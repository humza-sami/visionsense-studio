#include "visionsense/http_server.hpp"

#include <algorithm>
#include <arpa/inet.h>
#include <chrono>
#include <cerrno>
#include <csignal>
#include <cstring>
#include <iostream>
#include <netinet/in.h>
#include <optional>
#include <sstream>
#include <string>
#include <sys/socket.h>
#include <thread>
#include <unistd.h>
#include <utility>
#include <vector>

namespace visionsense {
namespace {

std::string response(
    const int status,
    const std::string& status_text,
    const std::string& body
) {
    return "HTTP/1.1 " + std::to_string(status) + " " + status_text + "\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: " + std::to_string(body.size()) + "\r\n"
        "Connection: close\r\n"
        "Access-Control-Allow-Origin: *\r\n"
        "Access-Control-Allow-Methods: GET, POST, DELETE, OPTIONS\r\n"
        "Access-Control-Allow-Headers: Content-Type\r\n\r\n" + body;
}

struct Request {
    std::string method;
    std::string path;
    std::string body;
};

Request parse_request(const std::string& request) {
    Request result;
    const auto first_space = request.find(' ');
    if (first_space == std::string::npos) return result;
    const auto second_space = request.find(' ', first_space + 1);
    if (second_space == std::string::npos) return result;
    result.method = request.substr(0, first_space);
    result.path = request.substr(first_space + 1, second_space - first_space - 1);
    const auto body_start = request.find("\r\n\r\n");
    if (body_start != std::string::npos) result.body = request.substr(body_start + 4);
    return result;
}

std::optional<std::string> json_string(
    const std::string& json,
    const std::string& key
) {
    const std::string token = "\"" + key + "\"";
    auto position = json.find(token);
    if (position == std::string::npos) return std::nullopt;
    position = json.find(':', position + token.size());
    if (position == std::string::npos) return std::nullopt;
    position = json.find('"', position + 1);
    if (position == std::string::npos) return std::nullopt;

    std::string value;
    bool escaped = false;
    for (++position; position < json.size(); ++position) {
        const char character = json[position];
        if (escaped) {
            switch (character) {
                case '"': value.push_back('"'); break;
                case '\\': value.push_back('\\'); break;
                case '/': value.push_back('/'); break;
                case 'b': value.push_back('\b'); break;
                case 'f': value.push_back('\f'); break;
                case 'n': value.push_back('\n'); break;
                case 'r': value.push_back('\r'); break;
                case 't': value.push_back('\t'); break;
                default: value.push_back(character); break;
            }
            escaped = false;
        } else if (character == '\\') {
            escaped = true;
        } else if (character == '"') {
            return value;
        } else {
            value.push_back(character);
        }
    }
    return std::nullopt;
}

std::string json_escape(const std::string& value) {
    std::ostringstream output;
    for (const char character : value) {
        if (character == '"' || character == '\\') output << '\\';
        output << character;
    }
    return output.str();
}

std::size_t content_length(const std::string& request) {
    constexpr const char* header = "Content-Length:";
    const auto position = request.find(header);
    if (position == std::string::npos) return 0;
    const auto start = request.find_first_not_of(' ', position + std::strlen(header));
    if (start == std::string::npos) return 0;
    try {
        return static_cast<std::size_t>(std::stoul(request.substr(start)));
    } catch (...) {
        return 0;
    }
}

bool send_all(const int socket_fd, const char* data, std::size_t size) {
    while (size > 0) {
        const auto sent = send(socket_fd, data, size, 0);
        if (sent <= 0) return false;
        data += sent;
        size -= static_cast<std::size_t>(sent);
    }
    return true;
}

}  // namespace

HttpServer::HttpServer(const std::uint16_t port, Capabilities capabilities)
    : port_(port), capabilities_(std::move(capabilities)) {}

void HttpServer::stop() {
    running_.store(false);
}

int HttpServer::run() {
    const int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0) {
        std::cerr << "Failed to create server socket\n";
        return 1;
    }

    int reuse = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));

    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_ANY);
    address.sin_port = htons(port_);

    if (bind(server_fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) < 0) {
        std::cerr << "Failed to bind media agent on port " << port_ << ": "
                  << std::strerror(errno) << '\n';
        close(server_fd);
        return 1;
    }

    if (listen(server_fd, 16) < 0) {
        std::cerr << "Failed to listen on media agent socket\n";
        close(server_fd);
        return 1;
    }

    std::cout << "VisionSense media agent listening on http://0.0.0.0:"
              << port_ << '\n';

    while (running_.load()) {
        const int client_fd = accept(server_fd, nullptr, nullptr);
        if (client_fd < 0) {
            if (errno == EINTR) continue;
            break;
        }

        std::thread([this, client_fd] {
            std::string raw_request;
            char buffer[4096]{};
            while (raw_request.find("\r\n\r\n") == std::string::npos) {
                const auto bytes_read = read(client_fd, buffer, sizeof(buffer));
                if (bytes_read <= 0) break;
                raw_request.append(buffer, static_cast<std::size_t>(bytes_read));
                if (raw_request.size() > 1024 * 1024) break;
            }
            const auto headers_end = raw_request.find("\r\n\r\n");
            const auto expected_body = content_length(raw_request);
            auto received_body = headers_end == std::string::npos
                ? std::size_t{0}
                : raw_request.size() - headers_end - 4;
            while (received_body < expected_body) {
                const auto bytes_read = read(client_fd, buffer, sizeof(buffer));
                if (bytes_read <= 0) break;
                raw_request.append(buffer, static_cast<std::size_t>(bytes_read));
                received_body += static_cast<std::size_t>(bytes_read);
            }
            const Request request = parse_request(raw_request);

            std::string payload;
            if (request.method == "OPTIONS") {
                payload = response(204, "No Content", "");
            } else if (request.method == "GET" && request.path == "/health") {
                payload = response(200, "OK", "{\"status\":\"ok\",\"service\":\"media-agent\"}");
            } else if (
                request.method == "GET"
                && request.path == "/v1/capabilities"
            ) {
                payload = response(200, "OK", capabilities_.to_json());
            } else if (
                request.method == "GET"
                && request.path == "/v1/pipelines"
            ) {
                payload = response(200, "OK", pipelines_.snapshots_json());
            } else if (
                request.method == "GET"
                && request.path.rfind("/v1/streams/", 0) == 0
                && request.path.size() > std::strlen("/v1/streams/")
            ) {
                const std::string id = request.path.substr(
                    std::strlen("/v1/streams/")
                );
                const std::string headers =
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
                    "Cache-Control: no-cache, no-store, must-revalidate\r\n"
                    "Connection: close\r\n"
                    "Access-Control-Allow-Origin: *\r\n\r\n";
                if (!send_all(client_fd, headers.data(), headers.size())) {
                    close(client_fd);
                    return;
                }
                std::uint64_t sequence = 0;
                std::vector<unsigned char> jpeg;
                constexpr auto frame_interval = std::chrono::microseconds(66'667);
                auto next_send = std::chrono::steady_clock::now();
                while (running_.load()) {
                    if (!pipelines_.wait_for_frame(
                        id,
                        sequence,
                        jpeg,
                        std::chrono::milliseconds(1500)
                    )) {
                        const auto snapshots = pipelines_.snapshots();
                        const bool exists = std::any_of(
                            snapshots.begin(),
                            snapshots.end(),
                            [&](const auto& item) { return item.id == id; }
                        );
                        if (!exists) break;
                        continue;
                    }
                    const auto now = std::chrono::steady_clock::now();
                    if (next_send > now) {
                        std::this_thread::sleep_until(next_send);
                    } else if (now - next_send > frame_interval) {
                        // Never "catch up" by dumping queued frames in a burst.
                        next_send = now;
                    }
                    const std::string part_header =
                        "--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                        + std::to_string(jpeg.size()) + "\r\n\r\n";
                    if (
                        !send_all(client_fd, part_header.data(), part_header.size())
                        || !send_all(
                            client_fd,
                            reinterpret_cast<const char*>(jpeg.data()),
                            jpeg.size()
                        )
                        || !send_all(client_fd, "\r\n", 2)
                    ) {
                        break;
                    }
                    next_send += frame_interval;
                }
                close(client_fd);
                return;
            } else if (
                request.path.rfind("/v1/pipelines/", 0) == 0
                && request.path.size() > std::strlen("/v1/pipelines/")
            ) {
                const std::string id = request.path.substr(
                    std::strlen("/v1/pipelines/")
                );
                if (request.method == "POST") {
                    const auto uri = json_string(request.body, "uri");
                    if (!uri.has_value()) {
                        payload = response(
                            422,
                            "Unprocessable Entity",
                            "{\"detail\":\"uri is required\"}"
                        );
                    } else {
                        std::string error;
                        if (pipelines_.start(id, *uri, error)) {
                            payload = response(
                                201,
                                "Created",
                                "{\"id\":\"" + json_escape(id)
                                    + "\",\"state\":\"connecting\"}"
                            );
                        } else {
                            payload = response(
                                400,
                                "Bad Request",
                                "{\"detail\":\"" + json_escape(error) + "\"}"
                            );
                        }
                    }
                } else if (request.method == "DELETE") {
                    pipelines_.stop(id);
                    payload = response(200, "OK", "{\"status\":\"stopped\"}");
                } else {
                    payload = response(
                        405,
                        "Method Not Allowed",
                        "{\"detail\":\"Method not allowed\"}"
                    );
                }
            } else {
                payload = response(404, "Not Found", "{\"detail\":\"Not found\"}");
            }

            send_all(client_fd, payload.data(), payload.size());
            close(client_fd);
        }).detach();
    }

    close(server_fd);
    return 0;
}

}  // namespace visionsense
