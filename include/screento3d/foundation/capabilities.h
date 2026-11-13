#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace screento3d {

enum class Availability {
    available,
    unavailable,
    unknown,
};

struct ComponentCapability {
    Availability availability{Availability::unknown};
    std::string version;
    std::string diagnostic;
};

struct GpuCapability {
    int ordinal{-1};
    std::string name;
    int compute_major{0};
    int compute_minor{0};
    std::uint64_t total_memory_bytes{0};
};

struct SystemCapabilities {
    std::string schema_version{"1"};
    std::string platform;
    ComponentCapability nvidia_driver;
    ComponentCapability cuda_driver;
    ComponentCapability nvdec_loader;
    ComponentCapability nvenc_loader;
    ComponentCapability tensorrt;
    ComponentCapability ffmpeg;
    ComponentCapability ffprobe;
    std::vector<GpuCapability> gpus;
};

[[nodiscard]] SystemCapabilities probe_system_capabilities();
[[nodiscard]] std::string to_json(const SystemCapabilities& capabilities, bool pretty);
[[nodiscard]] std::string_view to_string(Availability availability) noexcept;

}  // namespace screento3d
