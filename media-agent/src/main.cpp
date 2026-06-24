#include "visionsense/capabilities.hpp"
#include "visionsense/http_server.hpp"

#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <string>

int main(const int argc, char** argv) {
    std::uint16_t port = 9010;
    bool probe_only = false;

    for (int index = 1; index < argc; ++index) {
        const std::string argument = argv[index];
        if (argument == "--probe") {
            probe_only = true;
        } else if (argument == "--port" && index + 1 < argc) {
            const int parsed = std::atoi(argv[++index]);
            if (parsed <= 0 || parsed > 65535) {
                std::cerr << "Invalid port\n";
                return 2;
            }
            port = static_cast<std::uint16_t>(parsed);
        } else if (argument == "--help") {
            std::cout
                << "Usage: visionsense-media-agent [--probe] [--port 9010]\n"
                << "  --probe      Print hardware capabilities and exit\n"
                << "  --port PORT  HTTP control API port (default: 9010)\n";
            return 0;
        }
    }

    auto capabilities = visionsense::detect_capabilities();
    if (probe_only) {
        std::cout << capabilities.to_json() << '\n';
        return 0;
    }

    visionsense::HttpServer server(port, std::move(capabilities));
    return server.run();
}
