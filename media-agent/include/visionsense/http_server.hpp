#pragma once

#include <atomic>
#include <cstdint>
#include <memory>

#include "visionsense/capabilities.hpp"
#include "visionsense/pipeline_manager.hpp"

namespace visionsense {

class HttpServer {
public:
    HttpServer(std::uint16_t port, Capabilities capabilities);

    int run();
    void stop();

private:
    std::uint16_t port_;
    Capabilities capabilities_;
    PipelineManager pipelines_;
    std::atomic<bool> running_{true};
};

}  // namespace visionsense
