cmake_minimum_required(VERSION 3.20)

project(visionsense_media_agent VERSION 0.1.0 LANGUAGES CXX)

find_package(PkgConfig REQUIRED)
pkg_check_modules(
    GSTREAMER REQUIRED IMPORTED_TARGET
    gstreamer-1.0
    gstreamer-app-1.0
)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(visionsense-media-agent
    src/main.cpp
    src/capabilities.cpp
    src/http_server.cpp
    src/pipeline_manager.cpp
)

target_include_directories(visionsense-media-agent PRIVATE include)
target_link_libraries(visionsense-media-agent PRIVATE PkgConfig::GSTREAMER)

if(APPLE)
    target_compile_definitions(visionsense-media-agent PRIVATE VS_PLATFORM_MACOS=1)
elseif(UNIX)
    target_compile_definitions(visionsense-media-agent PRIVATE VS_PLATFORM_LINUX=1)
endif()

target_compile_options(visionsense-media-agent PRIVATE
    -Wall
    -Wextra
    -Wpedantic
)

install(TARGETS visionsense-media-agent RUNTIME DESTINATION bin)
