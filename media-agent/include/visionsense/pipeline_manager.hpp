#pragma once

#include <atomic>
#include <chrono>
#include <cstdint>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

namespace visionsense {

struct PipelineSnapshot {
    std::string id;
    std::string state;
    std::string error;
    std::string transport;
    std::string whep_url;
    std::uint64_t frames = 0;
    double fps = 0.0;
    int width = 0;
    int height = 0;
    std::uint64_t restarts = 0;
    std::size_t buffered_frames = 0;
    std::uint64_t dropped_for_clients = 0;
};

class PipelineManager {
public:
    struct Entry;

    PipelineManager();
    ~PipelineManager();

    PipelineManager(const PipelineManager&) = delete;
    PipelineManager& operator=(const PipelineManager&) = delete;

    bool start(const std::string& id, const std::string& uri, std::string& error);
    bool stop(const std::string& id);
    void stop_all();
    bool wait_for_frame(
        const std::string& id,
        std::uint64_t& sequence,
        std::vector<unsigned char>& jpeg,
        std::chrono::milliseconds timeout
    ) const;

    std::vector<PipelineSnapshot> snapshots() const;
    std::string snapshots_json() const;

private:
    void monitor();

    mutable std::mutex mutex_;
    std::unordered_map<std::string, std::shared_ptr<Entry>> entries_;
    std::atomic<bool> running_{true};
    std::unique_ptr<class PipelineMonitorThread> monitor_thread_;
};

}  // namespace visionsense
