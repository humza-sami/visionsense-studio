#include "visionsense/pipeline_manager.hpp"

#include <gst/gst.h>
#include <gst/app/gstappsink.h>

#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <deque>
#include <iomanip>
#include <sstream>
#include <thread>
#include <utility>

namespace visionsense {
namespace {

constexpr std::size_t kFrameBufferCapacity = 30;  // 2 seconds at 15 FPS.
constexpr std::size_t kPlaybackPrebuffer = 5;     // About 330 ms.
constexpr std::uint64_t kClientLagLimit = 10;     // Skip stale backlog.
constexpr int kWebRtcFps = 25;
constexpr int kMjpegFallbackFps = 15;

std::string json_escape(const std::string& value) {
    std::ostringstream output;
    for (const unsigned char character : value) {
        switch (character) {
            case '"': output << "\\\""; break;
            case '\\': output << "\\\\"; break;
            case '\b': output << "\\b"; break;
            case '\f': output << "\\f"; break;
            case '\n': output << "\\n"; break;
            case '\r': output << "\\r"; break;
            case '\t': output << "\\t"; break;
            default:
                if (character < 0x20) {
                    output << "\\u"
                           << std::hex << std::setw(4) << std::setfill('0')
                           << static_cast<int>(character)
                           << std::dec << std::setfill(' ');
                } else {
                    output << character;
                }
        }
    }
    return output.str();
}

std::string state_name(const GstState state) {
    switch (state) {
        case GST_STATE_VOID_PENDING: return "pending";
        case GST_STATE_NULL: return "stopped";
        case GST_STATE_READY: return "ready";
        case GST_STATE_PAUSED: return "connecting";
        case GST_STATE_PLAYING: return "live";
        default: return "unknown";
    }
}

std::string environment_or(const char* name, const char* fallback) {
    const char* value = std::getenv(name);
    return value != nullptr && value[0] != '\0' ? value : fallback;
}

void set_boolean_if_supported(
    GstElement* element,
    const char* property,
    const gboolean value
) {
    if (g_object_class_find_property(G_OBJECT_GET_CLASS(element), property)) {
        g_object_set(element, property, value, nullptr);
    }
}

void set_uint_if_supported(
    GstElement* element,
    const char* property,
    const guint value
) {
    if (g_object_class_find_property(G_OBJECT_GET_CLASS(element), property)) {
        g_object_set(element, property, value, nullptr);
    }
}

void set_int_if_supported(
    GstElement* element,
    const char* property,
    const gint value
) {
    if (g_object_class_find_property(G_OBJECT_GET_CLASS(element), property)) {
        g_object_set(element, property, value, nullptr);
    }
}

GstElement* make_h264_encoder(std::string& encoder_name) {
#if defined(VS_PLATFORM_MACOS)
    constexpr const char* candidates[] = {"vtenc_h264_hw", "vtenc_h264"};
#elif defined(VS_PLATFORM_LINUX)
    constexpr const char* candidates[] = {"nvh264enc", "x264enc"};
#else
    constexpr const char* candidates[] = {"x264enc"};
#endif
    for (const char* candidate : candidates) {
        if (GstElement* encoder = gst_element_factory_make(candidate, nullptr)) {
            encoder_name = candidate;
            return encoder;
        }
    }
    return nullptr;
}

}  // namespace

struct PipelineManager::Entry {
    struct BufferedFrame {
        std::uint64_t sequence = 0;
        std::vector<unsigned char> jpeg;
    };

    std::string id;
    std::string uri;
    GstElement* pipeline = nullptr;
    GstElement* queue = nullptr;
    GstElement* sink = nullptr;
    GstElement* publisher = nullptr;
    std::string encoder;
    std::string whep_url;
    std::atomic<std::uint64_t> frames{0};
    std::atomic<int> width{0};
    std::atomic<int> height{0};
    mutable std::mutex status_mutex;
    std::string state{"connecting"};
    std::string error;
    std::chrono::steady_clock::time_point started_at{
        std::chrono::steady_clock::now()
    };
    mutable std::mutex frame_mutex;
    std::condition_variable frame_ready;
    std::deque<BufferedFrame> frame_buffer;
    std::uint64_t frame_sequence = 0;
    std::atomic<std::uint64_t> dropped_for_clients{0};
    mutable std::mutex timing_mutex;
    std::deque<std::chrono::steady_clock::time_point> frame_times;
    std::chrono::steady_clock::time_point last_frame_at{
        std::chrono::steady_clock::now()
    };
    std::atomic<std::uint64_t> restarts{0};
    std::chrono::steady_clock::time_point last_restart{
        std::chrono::steady_clock::now()
    };
};

class PipelineMonitorThread {
public:
    template <typename Function>
    explicit PipelineMonitorThread(Function&& function)
        : thread_(std::forward<Function>(function)) {}

    ~PipelineMonitorThread() {
        if (thread_.joinable()) thread_.join();
    }

private:
    std::thread thread_;
};

namespace {

void on_source_setup(
    GstElement*,
    GstElement* source,
    gpointer
) {
    auto* object_class = G_OBJECT_GET_CLASS(source);
    if (g_object_class_find_property(object_class, "latency") != nullptr) {
        // Remote NVR packets arrive in bursts. The former 100 ms buffer
        // created visible 200+ ms pauses despite a high average FPS.
        g_object_set(source, "latency", 500, nullptr);
    }
    if (g_object_class_find_property(object_class, "drop-on-latency") != nullptr) {
        g_object_set(source, "drop-on-latency", FALSE, nullptr);
    }
    if (g_object_class_find_property(object_class, "protocols") != nullptr) {
        // GstRTSPLowerTrans TCP is bit 2. Avoid a direct gst-rtsp dependency.
        g_object_set(source, "protocols", 4, nullptr);
    }
}

void on_pad_added(
    GstElement*,
    GstPad* new_pad,
    gpointer user_data
) {
    auto* entry = static_cast<PipelineManager::Entry*>(user_data);
    GstCaps* caps = gst_pad_get_current_caps(new_pad);
    if (caps == nullptr) caps = gst_pad_query_caps(new_pad, nullptr);
    if (caps == nullptr || gst_caps_is_empty(caps)) {
        if (caps != nullptr) gst_caps_unref(caps);
        return;
    }

    const GstStructure* structure = gst_caps_get_structure(caps, 0);
    const char* media_type = gst_structure_get_name(structure);
    const bool is_video = g_str_has_prefix(media_type, "video/");
    if (is_video) {
        GstPad* sink_pad = gst_element_get_static_pad(entry->queue, "sink");
        if (sink_pad != nullptr && !gst_pad_is_linked(sink_pad)) {
            gst_pad_link(new_pad, sink_pad);
        }
        if (sink_pad != nullptr) gst_object_unref(sink_pad);
    }
    gst_caps_unref(caps);
}

GstFlowReturn on_sample(
    GstAppSink* sink,
    gpointer user_data
) {
    auto* entry = static_cast<PipelineManager::Entry*>(user_data);
    GstSample* sample = gst_app_sink_pull_sample(sink);
    if (sample == nullptr) return GST_FLOW_EOS;

    GstCaps* caps = gst_sample_get_caps(sample);
    if (caps != nullptr && !gst_caps_is_empty(caps)) {
        const GstStructure* structure = gst_caps_get_structure(caps, 0);
        int width = 0;
        int height = 0;
        if (gst_structure_get_int(structure, "width", &width)) {
            entry->width.store(width, std::memory_order_relaxed);
        }
        if (gst_structure_get_int(structure, "height", &height)) {
            entry->height.store(height, std::memory_order_relaxed);
        }
    }

    GstBuffer* buffer = gst_sample_get_buffer(sample);
    GstMapInfo map{};
    if (buffer != nullptr && gst_buffer_map(buffer, &map, GST_MAP_READ)) {
        {
            std::lock_guard frame_lock(entry->frame_mutex);
            ++entry->frame_sequence;
            PipelineManager::Entry::BufferedFrame buffered;
            buffered.sequence = entry->frame_sequence;
            buffered.jpeg.assign(map.data, map.data + map.size);
            entry->frame_buffer.push_back(std::move(buffered));
            while (entry->frame_buffer.size() > kFrameBufferCapacity) {
                entry->frame_buffer.pop_front();
            }
        }
        entry->frame_ready.notify_all();
        gst_buffer_unmap(buffer, &map);
    }
    gst_sample_unref(sample);
    return GST_FLOW_OK;
}

GstPadProbeReturn on_video_frame(
    GstPad* pad,
    GstPadProbeInfo* info,
    gpointer user_data
) {
    if ((GST_PAD_PROBE_INFO_TYPE(info) & GST_PAD_PROBE_TYPE_BUFFER) == 0) {
        return GST_PAD_PROBE_OK;
    }

    auto* entry = static_cast<PipelineManager::Entry*>(user_data);
    entry->frames.fetch_add(1, std::memory_order_relaxed);
    if (GstCaps* caps = gst_pad_get_current_caps(pad)) {
        if (!gst_caps_is_empty(caps)) {
            const GstStructure* structure = gst_caps_get_structure(caps, 0);
            int width = 0;
            int height = 0;
            if (gst_structure_get_int(structure, "width", &width)) {
                entry->width.store(width, std::memory_order_relaxed);
            }
            if (gst_structure_get_int(structure, "height", &height)) {
                entry->height.store(height, std::memory_order_relaxed);
            }
        }
        gst_caps_unref(caps);
    }

    const auto now = std::chrono::steady_clock::now();
    {
        std::lock_guard timing_lock(entry->timing_mutex);
        entry->last_frame_at = now;
        entry->frame_times.push_back(now);
        while (
            !entry->frame_times.empty()
            && now - entry->frame_times.front() > std::chrono::seconds(3)
        ) {
            entry->frame_times.pop_front();
        }
    }
    return GST_PAD_PROBE_OK;
}

}  // namespace

PipelineManager::PipelineManager() {
    gst_init(nullptr, nullptr);
    monitor_thread_ = std::make_unique<PipelineMonitorThread>(
        [this] { monitor(); }
    );
}

PipelineManager::~PipelineManager() {
    running_.store(false);
    monitor_thread_.reset();
    stop_all();
}

bool PipelineManager::start(
    const std::string& id,
    const std::string& uri,
    std::string& error
) {
    if (id.empty() || uri.empty()) {
        error = "pipeline id and uri are required";
        return false;
    }
    if (uri.rfind("rtsp://", 0) != 0 && uri.rfind("rtsps://", 0) != 0) {
        error = "only RTSP sources are supported by the native pipeline";
        return false;
    }

    stop(id);

    auto entry = std::make_shared<Entry>();
    entry->id = id;
    entry->uri = uri;
    entry->pipeline = gst_pipeline_new(("pipeline-" + id).c_str());
    GstElement* source = gst_element_factory_make("uridecodebin", nullptr);
    entry->queue = gst_element_factory_make("queue", nullptr);
    GstElement* convert = gst_element_factory_make("videoconvert", nullptr);
    GstElement* scale = gst_element_factory_make("videoscale", nullptr);
    GstElement* source_rate = gst_element_factory_make("videorate", nullptr);
    GstElement* source_caps = gst_element_factory_make("capsfilter", nullptr);
    GstElement* tee = gst_element_factory_make("tee", nullptr);

    GstElement* webrtc_queue = gst_element_factory_make("queue", nullptr);
    GstElement* encoder = make_h264_encoder(entry->encoder);
    GstElement* parser = gst_element_factory_make("h264parse", nullptr);
    GstElement* h264_caps = gst_element_factory_make("capsfilter", nullptr);
    entry->publisher = gst_element_factory_make("rtspclientsink", nullptr);

    GstElement* fallback_queue = gst_element_factory_make("queue", nullptr);
    GstElement* fallback_rate = gst_element_factory_make("videorate", nullptr);
    GstElement* fallback_caps = gst_element_factory_make("capsfilter", nullptr);
    GstElement* jpeg = gst_element_factory_make("jpegenc", nullptr);
    entry->sink = gst_element_factory_make("appsink", nullptr);

    if (
        entry->pipeline == nullptr
        || source == nullptr
        || entry->queue == nullptr
        || convert == nullptr
        || scale == nullptr
        || source_rate == nullptr
        || source_caps == nullptr
        || tee == nullptr
        || webrtc_queue == nullptr
        || encoder == nullptr
        || parser == nullptr
        || h264_caps == nullptr
        || entry->publisher == nullptr
        || fallback_queue == nullptr
        || fallback_rate == nullptr
        || fallback_caps == nullptr
        || jpeg == nullptr
        || entry->sink == nullptr
    ) {
        error = "required GStreamer/RTSP publishing elements are unavailable";
        if (entry->pipeline != nullptr) gst_object_unref(entry->pipeline);
        entry->pipeline = nullptr;
        return false;
    }

    g_object_set(source, "uri", uri.c_str(), nullptr);
    g_object_set(
        entry->queue,
        "leaky", 2,
        "max-size-buffers", 2,
        "max-size-bytes", 0,
        "max-size-time", static_cast<guint64>(0),
        nullptr
    );
    GstCaps* source_output_caps = gst_caps_new_simple(
        "video/x-raw",
        "format", G_TYPE_STRING, "NV12",
        "width", G_TYPE_INT, 1280,
        "height", G_TYPE_INT, 720,
        "framerate", GST_TYPE_FRACTION, kWebRtcFps, 1,
        "pixel-aspect-ratio", GST_TYPE_FRACTION, 1, 1,
        nullptr
    );
    g_object_set(source_caps, "caps", source_output_caps, nullptr);
    gst_caps_unref(source_output_caps);
    g_object_set(source_rate, "drop-only", FALSE, "skip-to-first", TRUE, nullptr);

    g_object_set(
        webrtc_queue,
        "leaky", 2,
        "max-size-buffers", 2,
        "max-size-bytes", 0,
        "max-size-time", static_cast<guint64>(0),
        nullptr
    );
    set_boolean_if_supported(encoder, "realtime", TRUE);
    set_boolean_if_supported(encoder, "allow-frame-reordering", FALSE);
    set_boolean_if_supported(encoder, "zerolatency", TRUE);
    set_uint_if_supported(encoder, "bitrate", 3000);
    set_int_if_supported(encoder, "max-keyframe-interval", 50);
    set_int_if_supported(encoder, "gop-size", 50);
    g_object_set(parser, "config-interval", -1, nullptr);
    GstCaps* encoded_caps = gst_caps_new_simple(
        "video/x-h264",
        "profile", G_TYPE_STRING, "baseline",
        "stream-format", G_TYPE_STRING, "avc",
        "alignment", G_TYPE_STRING, "au",
        nullptr
    );
    g_object_set(h264_caps, "caps", encoded_caps, nullptr);
    gst_caps_unref(encoded_caps);

    const std::string publish_base = environment_or(
        "VS_MEDIA_PUBLISH_BASE",
        "rtsp://127.0.0.1:8554"
    );
    const std::string public_base = environment_or(
        "VS_WEBRTC_PUBLIC_BASE",
        "http://localhost:8889"
    );
    const std::string publish_endpoint = publish_base + "/" + id;
    entry->whep_url = public_base + "/" + id + "/whep";
    g_object_set(
        entry->publisher,
        "location", publish_endpoint.c_str(),
        "protocols", 4,
        nullptr
    );

    g_object_set(
        fallback_queue,
        "leaky", 2,
        "max-size-buffers", 2,
        "max-size-bytes", 0,
        "max-size-time", static_cast<guint64>(0),
        nullptr
    );
    g_object_set(fallback_rate, "drop-only", TRUE, "skip-to-first", TRUE, nullptr);
    GstCaps* fallback_output_caps = gst_caps_new_simple(
        "video/x-raw",
        "framerate", GST_TYPE_FRACTION, kMjpegFallbackFps, 1,
        nullptr
    );
    g_object_set(fallback_caps, "caps", fallback_output_caps, nullptr);
    gst_caps_unref(fallback_output_caps);
    g_object_set(jpeg, "quality", 65, nullptr);
    g_object_set(
        entry->sink,
        // Honor videorate timestamps so catch-up frames are not dumped in a
        // burst after an RTSP pause.
        "sync", TRUE,
        "emit-signals", TRUE,
        "max-buffers", 1,
        "drop", TRUE,
        nullptr
    );

    gst_bin_add_many(
        GST_BIN(entry->pipeline),
        source,
        entry->queue,
        convert,
        scale,
        source_rate,
        source_caps,
        tee,
        webrtc_queue,
        encoder,
        parser,
        h264_caps,
        entry->publisher,
        fallback_queue,
        fallback_rate,
        fallback_caps,
        jpeg,
        entry->sink,
        nullptr
    );
    if (!gst_element_link_many(
        entry->queue,
        convert,
        scale,
        source_rate,
        source_caps,
        tee,
        nullptr
    ) || !gst_element_link_many(
        tee,
        webrtc_queue,
        encoder,
        parser,
        h264_caps,
        entry->publisher,
        nullptr
    ) || !gst_element_link_many(
        tee,
        fallback_queue,
        fallback_rate,
        fallback_caps,
        jpeg,
        entry->sink,
        nullptr
    )) {
        error = "failed to link native WebRTC/fallback pipeline";
        gst_object_unref(entry->pipeline);
        entry->pipeline = nullptr;
        return false;
    }

    g_signal_connect(source, "source-setup", G_CALLBACK(on_source_setup), entry.get());
    g_signal_connect(source, "pad-added", G_CALLBACK(on_pad_added), entry.get());

    g_signal_connect(entry->sink, "new-sample", G_CALLBACK(on_sample), entry.get());
    if (GstPad* source_pad = gst_element_get_static_pad(source_caps, "src")) {
        gst_pad_add_probe(
            source_pad,
            GST_PAD_PROBE_TYPE_BUFFER,
            on_video_frame,
            entry.get(),
            nullptr
        );
        gst_object_unref(source_pad);
    }

    {
        std::lock_guard lock(mutex_);
        entries_[id] = entry;
    }

    const GstStateChangeReturn result = gst_element_set_state(
        entry->pipeline,
        GST_STATE_PLAYING
    );
    if (result == GST_STATE_CHANGE_FAILURE) {
        error = "GStreamer rejected the RTSP pipeline";
        stop(id);
        return false;
    }
    return true;
}

bool PipelineManager::stop(const std::string& id) {
    std::shared_ptr<Entry> entry;
    {
        std::lock_guard lock(mutex_);
        const auto iterator = entries_.find(id);
        if (iterator == entries_.end()) return false;
        entry = iterator->second;
        entries_.erase(iterator);
    }

    if (entry->pipeline != nullptr) {
        gst_element_set_state(entry->pipeline, GST_STATE_NULL);
        gst_element_get_state(
            entry->pipeline,
            nullptr,
            nullptr,
            2 * GST_SECOND
        );
        gst_object_unref(entry->pipeline);
        entry->pipeline = nullptr;
    }
    return true;
}

void PipelineManager::stop_all() {
    std::vector<std::string> ids;
    {
        std::lock_guard lock(mutex_);
        ids.reserve(entries_.size());
        for (const auto& [id, _] : entries_) ids.push_back(id);
    }
    for (const auto& id : ids) stop(id);
}

bool PipelineManager::wait_for_frame(
    const std::string& id,
    std::uint64_t& sequence,
    std::vector<unsigned char>& jpeg,
    const std::chrono::milliseconds timeout
) const {
    std::shared_ptr<Entry> entry;
    {
        std::lock_guard lock(mutex_);
        const auto iterator = entries_.find(id);
        if (iterator == entries_.end()) return false;
        entry = iterator->second;
    }

    std::unique_lock frame_lock(entry->frame_mutex);
    entry->frame_ready.wait_for(frame_lock, timeout, [&] {
        if (!running_.load()) return true;
        if (entry->frame_buffer.empty()) return false;
        if (sequence == 0) {
            return entry->frame_buffer.size() >= kPlaybackPrebuffer;
        }
        return entry->frame_buffer.back().sequence > sequence;
    });

    if (entry->frame_buffer.empty()) return false;
    const auto& newest = entry->frame_buffer.back();

    std::size_t selected_index = 0;
    if (sequence == 0) {
        selected_index = entry->frame_buffer.size() > kPlaybackPrebuffer
            ? entry->frame_buffer.size() - kPlaybackPrebuffer
            : 0;
    } else if (
        sequence < entry->frame_buffer.front().sequence
        || (
            newest.sequence > sequence
            && newest.sequence - sequence > kClientLagLimit
        )
    ) {
        selected_index = entry->frame_buffer.size() > kPlaybackPrebuffer
            ? entry->frame_buffer.size() - kPlaybackPrebuffer
            : 0;
        entry->dropped_for_clients.fetch_add(
            entry->frame_buffer[selected_index].sequence > sequence
                ? entry->frame_buffer[selected_index].sequence - sequence - 1
                : 0,
            std::memory_order_relaxed
        );
    } else {
        const auto iterator = std::find_if(
            entry->frame_buffer.begin(),
            entry->frame_buffer.end(),
            [&](const auto& frame) { return frame.sequence > sequence; }
        );
        if (iterator == entry->frame_buffer.end()) return false;
        selected_index = static_cast<std::size_t>(
            std::distance(entry->frame_buffer.begin(), iterator)
        );
    }

    const auto& selected = entry->frame_buffer[selected_index];
    sequence = selected.sequence;
    jpeg = selected.jpeg;
    return true;
}

std::vector<PipelineSnapshot> PipelineManager::snapshots() const {
    std::vector<std::shared_ptr<Entry>> entries;
    {
        std::lock_guard lock(mutex_);
        entries.reserve(entries_.size());
        for (const auto& [_, entry] : entries_) entries.push_back(entry);
    }

    std::vector<PipelineSnapshot> result;
    result.reserve(entries.size());
    for (const auto& entry : entries) {
        PipelineSnapshot snapshot;
        snapshot.id = entry->id;
        {
            std::lock_guard status_lock(entry->status_mutex);
            snapshot.state = entry->state;
            snapshot.error = entry->error;
        }
        snapshot.transport = "webrtc";
        snapshot.whep_url = entry->whep_url;
        snapshot.frames = entry->frames.load(std::memory_order_relaxed);
        snapshot.width = entry->width.load(std::memory_order_relaxed);
        snapshot.height = entry->height.load(std::memory_order_relaxed);
        snapshot.restarts = entry->restarts.load(std::memory_order_relaxed);
        snapshot.dropped_for_clients = entry->dropped_for_clients.load(
            std::memory_order_relaxed
        );
        {
            std::lock_guard frame_lock(entry->frame_mutex);
            snapshot.buffered_frames = entry->frame_buffer.size();
        }
        {
            std::lock_guard timing_lock(entry->timing_mutex);
            if (entry->frame_times.size() >= 2) {
                const double seconds = std::chrono::duration<double>(
                    entry->frame_times.back() - entry->frame_times.front()
                ).count();
                snapshot.fps = seconds > 0.0
                    ? static_cast<double>(entry->frame_times.size() - 1) / seconds
                    : 0.0;
            }
        }
        result.push_back(std::move(snapshot));
    }
    std::sort(result.begin(), result.end(), [](const auto& left, const auto& right) {
        return left.id < right.id;
    });
    return result;
}

std::string PipelineManager::snapshots_json() const {
    const auto current = snapshots();
    std::ostringstream output;
    output << "{\"pipelines\":[";
    for (std::size_t index = 0; index < current.size(); ++index) {
        if (index > 0) output << ',';
        const auto& item = current[index];
        output << "{\"id\":\"" << json_escape(item.id)
               << "\",\"state\":\"" << json_escape(item.state)
               << "\",\"error\":\"" << json_escape(item.error)
               << "\",\"transport\":\"" << json_escape(item.transport)
               << "\",\"whep_url\":\"" << json_escape(item.whep_url)
               << "\",\"frames\":" << item.frames
               << ",\"fps\":" << std::fixed << std::setprecision(2) << item.fps
               << ",\"width\":" << item.width
               << ",\"height\":" << item.height
               << ",\"restarts\":" << item.restarts
               << ",\"buffered_frames\":" << item.buffered_frames
               << ",\"dropped_for_clients\":" << item.dropped_for_clients
               << '}';
    }
    output << "]}";
    return output.str();
}

void PipelineManager::monitor() {
    while (running_.load()) {
        std::vector<std::shared_ptr<Entry>> entries;
        {
            std::lock_guard lock(mutex_);
            entries.reserve(entries_.size());
            for (const auto& [_, entry] : entries_) entries.push_back(entry);
        }

        for (const auto& entry : entries) {
            if (entry->pipeline == nullptr) continue;
            GstBus* bus = gst_element_get_bus(entry->pipeline);
            bool should_restart = false;
            while (true) {
                GstMessage* message = gst_bus_pop_filtered(
                    bus,
                    static_cast<GstMessageType>(
                        GST_MESSAGE_ERROR
                        | GST_MESSAGE_EOS
                        | GST_MESSAGE_STATE_CHANGED
                    )
                );
                if (message == nullptr) break;

                std::lock_guard status_lock(entry->status_mutex);
                if (GST_MESSAGE_TYPE(message) == GST_MESSAGE_ERROR) {
                    GError* gst_error = nullptr;
                    char* debug = nullptr;
                    gst_message_parse_error(message, &gst_error, &debug);
                    entry->state = "error";
                    entry->error = gst_error != nullptr
                        ? gst_error->message
                        : "unknown GStreamer error";
                    should_restart = true;
                    if (gst_error != nullptr) g_error_free(gst_error);
                    g_free(debug);
                } else if (GST_MESSAGE_TYPE(message) == GST_MESSAGE_EOS) {
                    entry->state = "error";
                    entry->error = "stream ended";
                    should_restart = true;
                } else if (
                    GST_MESSAGE_TYPE(message) == GST_MESSAGE_STATE_CHANGED
                    && GST_MESSAGE_SRC(message) == GST_OBJECT(entry->pipeline)
                ) {
                    GstState old_state;
                    GstState new_state;
                    GstState pending;
                    gst_message_parse_state_changed(
                        message,
                        &old_state,
                        &new_state,
                        &pending
                    );
                    (void)old_state;
                    (void)pending;
                    entry->state = state_name(new_state);
                    if (new_state == GST_STATE_PLAYING) entry->error.clear();
                }
                gst_message_unref(message);
            }
            gst_object_unref(bus);

            {
                std::lock_guard status_lock(entry->status_mutex);
                should_restart = should_restart || entry->state == "error";
            }
            if (!should_restart && entry->frames.load() > 0) {
                std::lock_guard timing_lock(entry->timing_mutex);
                if (
                    std::chrono::steady_clock::now() - entry->last_frame_at
                    > std::chrono::seconds(5)
                ) {
                    should_restart = true;
                    std::lock_guard status_lock(entry->status_mutex);
                    entry->state = "error";
                    entry->error = "frame timeout";
                }
            }
            if (should_restart) {
                const auto now = std::chrono::steady_clock::now();
                if (now - entry->last_restart >= std::chrono::seconds(2)) {
                    {
                        std::lock_guard status_lock(entry->status_mutex);
                        entry->state = "connecting";
                    }
                    gst_element_set_state(entry->pipeline, GST_STATE_NULL);
                    {
                        std::lock_guard frame_lock(entry->frame_mutex);
                        entry->frame_buffer.clear();
                    }
                    {
                        std::lock_guard timing_lock(entry->timing_mutex);
                        entry->last_frame_at = now;
                    }
                    gst_element_set_state(entry->pipeline, GST_STATE_PLAYING);
                    entry->last_restart = now;
                    entry->restarts.fetch_add(1, std::memory_order_relaxed);
                }
            }
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }
}

}  // namespace visionsense
