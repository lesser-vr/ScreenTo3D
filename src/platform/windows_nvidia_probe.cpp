#include "screento3d/foundation/capabilities.h"

#if defined(_WIN32)

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <array>
#include <cstddef>
#include <filesystem>
#include <optional>
#include <sstream>
#include <string>
#include <string_view>
#include <vector>

namespace screento3d {
namespace {

using CuResult = int;
using CuDevice = int;

constexpr CuResult kCudaSuccess = 0;

template <typename Function>
Function load_symbol(const HMODULE library, const char* name) {
    return reinterpret_cast<Function>(GetProcAddress(library, name));
}

std::string windows_error(const DWORD code) {
    LPSTR buffer = nullptr;
    const DWORD size = FormatMessageA(
        FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM |
            FORMAT_MESSAGE_IGNORE_INSERTS,
        nullptr, code, 0, reinterpret_cast<LPSTR>(&buffer), 0, nullptr);
    std::string message = size == 0 || buffer == nullptr
                              ? "Windows error " + std::to_string(code)
                              : std::string(buffer, size);
    if (buffer != nullptr) LocalFree(buffer);
    while (!message.empty() && (message.back() == '\r' || message.back() == '\n')) {
        message.pop_back();
    }
    return message;
}

ComponentCapability probe_library(const wchar_t* library_name,
                                  std::string_view available_message) {
    SetLastError(ERROR_SUCCESS);
    const HMODULE library = LoadLibraryExW(library_name, nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (library == nullptr) {
        const auto error = GetLastError();
        return {Availability::unavailable, "", windows_error(error)};
    }
    FreeLibrary(library);
    return {Availability::available, "", std::string(available_message)};
}

ComponentCapability find_executable(const wchar_t* executable_name) {
    std::array<wchar_t, 32768> path{};
    const DWORD length = SearchPathW(nullptr, executable_name, nullptr,
                                     static_cast<DWORD>(path.size()), path.data(), nullptr);
    if (length == 0 || length >= path.size()) {
        return {Availability::unavailable, "", "not found on PATH"};
    }
    return {Availability::available, "", "found on PATH"};
}

ComponentCapability probe_tensorrt() {
    constexpr std::array candidates{
        L"nvinfer_11.dll", L"nvinfer_10.dll", L"nvinfer.dll"};
    for (const auto* candidate : candidates) {
        SetLastError(ERROR_SUCCESS);
        const HMODULE library = LoadLibraryW(candidate);
        if (library != nullptr) {
            FreeLibrary(library);
            std::filesystem::path name(candidate);
            return {Availability::available, "", "loaded " + name.string()};
        }
    }
    return {Availability::unavailable, "",
            "TensorRT runtime DLL was not found on the DLL search path"};
}

void probe_cuda(SystemCapabilities& capabilities) {
    const HMODULE library = LoadLibraryExW(L"nvcuda.dll", nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (library == nullptr) {
        const auto diagnostic = windows_error(GetLastError());
        capabilities.nvidia_driver = {Availability::unavailable, "", diagnostic};
        capabilities.cuda_driver = {Availability::unavailable, "", diagnostic};
        return;
    }

    using CuInit = CuResult(__stdcall*)(unsigned int);
    using CuDriverGetVersion = CuResult(__stdcall*)(int*);
    using CuDeviceGetCount = CuResult(__stdcall*)(int*);
    using CuDeviceGetName = CuResult(__stdcall*)(char*, int, CuDevice);
    using CuDeviceComputeCapability = CuResult(__stdcall*)(int*, int*, CuDevice);
    using CuDeviceTotalMem = CuResult(__stdcall*)(std::size_t*, CuDevice);

    const auto cu_init = load_symbol<CuInit>(library, "cuInit");
    const auto cu_driver_get_version =
        load_symbol<CuDriverGetVersion>(library, "cuDriverGetVersion");
    const auto cu_device_get_count =
        load_symbol<CuDeviceGetCount>(library, "cuDeviceGetCount");
    const auto cu_device_get_name =
        load_symbol<CuDeviceGetName>(library, "cuDeviceGetName");
    const auto cu_device_compute_capability =
        load_symbol<CuDeviceComputeCapability>(library, "cuDeviceComputeCapability");
    auto cu_device_total_mem = load_symbol<CuDeviceTotalMem>(library, "cuDeviceTotalMem_v2");
    if (cu_device_total_mem == nullptr) {
        cu_device_total_mem = load_symbol<CuDeviceTotalMem>(library, "cuDeviceTotalMem");
    }

    if (cu_init == nullptr || cu_driver_get_version == nullptr ||
        cu_device_get_count == nullptr || cu_device_get_name == nullptr ||
        cu_device_compute_capability == nullptr || cu_device_total_mem == nullptr) {
        capabilities.nvidia_driver = {Availability::unavailable, "",
                                      "nvcuda.dll is missing required driver symbols"};
        capabilities.cuda_driver = capabilities.nvidia_driver;
        FreeLibrary(library);
        return;
    }

    const CuResult init_result = cu_init(0);
    if (init_result != kCudaSuccess) {
        capabilities.nvidia_driver = {Availability::available, "",
                                      "nvcuda.dll loaded"};
        capabilities.cuda_driver = {Availability::unavailable, "",
                                    "cuInit failed with code " + std::to_string(init_result)};
        FreeLibrary(library);
        return;
    }

    int driver_version = 0;
    const CuResult version_result = cu_driver_get_version(&driver_version);
    const auto version = version_result == kCudaSuccess
                             ? std::to_string(driver_version / 1000) + "." +
                                   std::to_string((driver_version % 1000) / 10)
                             : "";
    capabilities.nvidia_driver = {Availability::available, version,
                                  "NVIDIA CUDA driver initialized"};
    capabilities.cuda_driver = {Availability::available, version,
                                "CUDA Driver API is callable"};

    int device_count = 0;
    if (cu_device_get_count(&device_count) == kCudaSuccess) {
        for (int ordinal = 0; ordinal < device_count; ++ordinal) {
            std::array<char, 256> name{};
            int major = 0;
            int minor = 0;
            std::size_t total_memory = 0;
            if (cu_device_get_name(name.data(), static_cast<int>(name.size()), ordinal) !=
                    kCudaSuccess ||
                cu_device_compute_capability(&major, &minor, ordinal) != kCudaSuccess ||
                cu_device_total_mem(&total_memory, ordinal) != kCudaSuccess) {
                continue;
            }
            capabilities.gpus.push_back(
                {ordinal, name.data(), major, minor,
                 static_cast<std::uint64_t>(total_memory)});
        }
    }

    FreeLibrary(library);
}

}  // namespace

SystemCapabilities probe_system_capabilities() {
    SystemCapabilities capabilities;
    capabilities.platform = "windows";
    probe_cuda(capabilities);
    capabilities.nvdec_loader =
        probe_library(L"nvcuvid.dll", "NVDEC loader is available");
    capabilities.nvenc_loader =
        probe_library(L"nvEncodeAPI64.dll", "NVENC loader is available");
    capabilities.tensorrt = probe_tensorrt();
    capabilities.ffmpeg = find_executable(L"ffmpeg.exe");
    capabilities.ffprobe = find_executable(L"ffprobe.exe");
    return capabilities;
}

}  // namespace screento3d

#else

namespace screento3d {

SystemCapabilities probe_system_capabilities() {
    SystemCapabilities capabilities;
    capabilities.platform = "unsupported";
    capabilities.nvidia_driver = {Availability::unknown, "", "probe is Windows-only"};
    capabilities.cuda_driver = capabilities.nvidia_driver;
    capabilities.nvdec_loader = capabilities.nvidia_driver;
    capabilities.nvenc_loader = capabilities.nvidia_driver;
    capabilities.tensorrt = capabilities.nvidia_driver;
    capabilities.ffmpeg = capabilities.nvidia_driver;
    capabilities.ffprobe = capabilities.nvidia_driver;
    return capabilities;
}

}  // namespace screento3d

#endif
