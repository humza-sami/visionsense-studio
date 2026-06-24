#pragma once

#include <string>
#include <vector>

namespace visionsense {

struct Capabilities {
    std::string platform;
    std::string architecture;
    std::string video_backend;
    std::string inference_backend;
    bool ffmpeg_available{false};
    bool gstreamer_available{false};
    bool hardware_decode{false};
    bool hardware_encode{false};
    bool nvidia_gpu{false};
    bool rtsp_available{false};
    bool webrtc_available{false};
    std::vector<std::string> decoders;
    std::vector<std::string> encoders;

    [[nodiscard]] std::string to_json() const;
};

[[nodiscard]] Capabilities detect_capabilities();

}  // namespace visionsense
