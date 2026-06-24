#include "visionsense/capabilities.hpp"

#include <array>
#include <cstdlib>
#include <cstdio>
#include <sstream>
#include <string_view>
#include <sys/utsname.h>

namespace visionsense {
namespace {

std::string run_command(const char* command) {
    std::array<char, 512> buffer{};
    std::string output;
    FILE* pipe = popen(command, "r");
    if (pipe == nullptr) {
        return output;
    }
    while (fgets(buffer.data(), static_cast<int>(buffer.size()), pipe) != nullptr) {
        output.append(buffer.data());
    }
    pclose(pipe);
    return output;
}

bool command_succeeds(const char* command) {
    std::string wrapped = std::string(command) + " >/dev/null 2>&1";
    return std::system(wrapped.c_str()) == 0;
}

bool contains(std::string_view haystack, std::string_view needle) {
    return haystack.find(needle) != std::string_view::npos;
}

std::string json_escape(std::string_view value) {
    std::string escaped;
    escaped.reserve(value.size());
    for (const char ch : value) {
        switch (ch) {
            case '\\': escaped += "\\\\"; break;
            case '"': escaped += "\\\""; break;
            case '\n': escaped += "\\n"; break;
            case '\r': escaped += "\\r"; break;
            case '\t': escaped += "\\t"; break;
            default: escaped += ch; break;
        }
    }
    return escaped;
}

std::string json_array(const std::vector<std::string>& values) {
    std::ostringstream out;
    out << '[';
    for (std::size_t index = 0; index < values.size(); ++index) {
        if (index > 0) out << ',';
        out << '"' << json_escape(values[index]) << '"';
    }
    out << ']';
    return out.str();
}

}  // namespace

std::string Capabilities::to_json() const {
    std::ostringstream out;
    out << '{'
        << "\"platform\":\"" << json_escape(platform) << "\","
        << "\"architecture\":\"" << json_escape(architecture) << "\","
        << "\"video_backend\":\"" << json_escape(video_backend) << "\","
        << "\"inference_backend\":\"" << json_escape(inference_backend) << "\","
        << "\"ffmpeg_available\":" << (ffmpeg_available ? "true" : "false") << ','
        << "\"gstreamer_available\":" << (gstreamer_available ? "true" : "false") << ','
        << "\"hardware_decode\":" << (hardware_decode ? "true" : "false") << ','
        << "\"hardware_encode\":" << (hardware_encode ? "true" : "false") << ','
        << "\"nvidia_gpu\":" << (nvidia_gpu ? "true" : "false") << ','
        << "\"rtsp_available\":" << (rtsp_available ? "true" : "false") << ','
        << "\"webrtc_available\":" << (webrtc_available ? "true" : "false") << ','
        << "\"decoders\":" << json_array(decoders) << ','
        << "\"encoders\":" << json_array(encoders)
        << '}';
    return out.str();
}

Capabilities detect_capabilities() {
    Capabilities capabilities;
    struct utsname system_info {};
    if (uname(&system_info) == 0) {
        capabilities.platform = system_info.sysname;
        capabilities.architecture = system_info.machine;
    } else {
        capabilities.platform = "unknown";
        capabilities.architecture = "unknown";
    }

    capabilities.ffmpeg_available = command_succeeds("ffmpeg -version");
    capabilities.gstreamer_available = command_succeeds("gst-launch-1.0 --version");
    capabilities.rtsp_available = capabilities.gstreamer_available
        && command_succeeds("gst-inspect-1.0 rtspsrc");
    capabilities.webrtc_available = capabilities.gstreamer_available
        && command_succeeds("gst-inspect-1.0 webrtcbin");

    const std::string ffmpeg_hwaccels = capabilities.ffmpeg_available
        ? run_command("ffmpeg -hide_banner -hwaccels 2>/dev/null")
        : "";

#if defined(VS_PLATFORM_MACOS)
    const bool video_toolbox = contains(ffmpeg_hwaccels, "videotoolbox");
    const bool gst_video_toolbox = capabilities.gstreamer_available
        && command_succeeds("gst-inspect-1.0 vtdec_hw")
        && command_succeeds("gst-inspect-1.0 vtenc_h264_hw");
    capabilities.video_backend = (video_toolbox || gst_video_toolbox)
        ? "videotoolbox"
        : "software";
    capabilities.inference_backend = "coreml";
    capabilities.hardware_decode = video_toolbox || gst_video_toolbox;
    capabilities.hardware_encode = video_toolbox || gst_video_toolbox;
    if (capabilities.hardware_decode) {
        capabilities.decoders = gst_video_toolbox
            ? std::vector<std::string>{"vtdec_hw"}
            : std::vector<std::string>{"h264_videotoolbox", "hevc_videotoolbox"};
        capabilities.encoders = gst_video_toolbox
            ? std::vector<std::string>{"vtenc_h264_hw", "vtenc_h265_hw"}
            : std::vector<std::string>{"h264_videotoolbox", "hevc_videotoolbox"};
    }
#elif defined(VS_PLATFORM_LINUX)
    capabilities.nvidia_gpu = command_succeeds("nvidia-smi");
    const bool cuda_decode = capabilities.nvidia_gpu && contains(ffmpeg_hwaccels, "cuda");
    const bool gst_nvcodec = capabilities.gstreamer_available
        && command_succeeds("gst-inspect-1.0 nvh264dec")
        && command_succeeds("gst-inspect-1.0 nvh265dec");
    capabilities.video_backend = (cuda_decode || gst_nvcodec) ? "nvcodec" : "software";
    capabilities.inference_backend = capabilities.nvidia_gpu ? "tensorrt" : "cpu";
    capabilities.hardware_decode = cuda_decode || gst_nvcodec;
    capabilities.hardware_encode = capabilities.nvidia_gpu;
    if (capabilities.hardware_decode) {
        capabilities.decoders = {"nvh264dec", "nvh265dec"};
    }
    if (capabilities.hardware_encode) {
        capabilities.encoders = {"nvh264enc", "nvh265enc"};
    }
#else
    capabilities.video_backend = "software";
    capabilities.inference_backend = "cpu";
#endif

    return capabilities;
}

}  // namespace visionsense
