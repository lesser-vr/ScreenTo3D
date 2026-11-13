// Isolated ScreenTo3D probe using the pinned local DLSS project's MIT NVOF bridge.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <d3d11.h>
#include <dxgi1_4.h>
#include <wrl/client.h>

#include <chrono>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include "../../../dlss-nr-capture/third_party/comfyui_dlss5_nr/nvof_flow.cpp"

using Microsoft::WRL::ComPtr;

namespace {
thread_local std::string last_error;

struct ProbeTiming {
    uint64_t bgra_us;
    uint64_t upload_us;
    uint64_t nvof_us;
    uint32_t flow_width;
    uint32_t flow_height;
    uint32_t grid;
    uint32_t has_flow;
};

struct Probe {
    uint32_t width;
    uint32_t height;
    ComPtr<IDXGIAdapter1> adapter;
    ComPtr<ID3D11Device> device;
    ComPtr<ID3D11DeviceContext> context;
    ComPtr<ID3D11Texture2D> input;
    std::vector<uint8_t> bgra;
    std::thread::id owner = std::this_thread::get_id();

    Probe(uint32_t w, uint32_t h) : width(w), height(h) {
        if (w < 16 || h < 16 || w > 4096 || h > 2160)
            throw std::runtime_error("Invalid NVOF probe dimensions");
        ComPtr<IDXGIFactory1> factory;
        if (FAILED(CreateDXGIFactory1(IID_PPV_ARGS(&factory))))
            throw std::runtime_error("DXGI factory creation failed");
        for (UINT i = 0;; ++i) {
            ComPtr<IDXGIAdapter1> candidate;
            const HRESULT result = factory->EnumAdapters1(i, &candidate);
            if (result == DXGI_ERROR_NOT_FOUND) break;
            if (FAILED(result)) throw std::runtime_error("DXGI enumeration failed");
            DXGI_ADAPTER_DESC1 desc{};
            if (FAILED(candidate->GetDesc1(&desc)))
                throw std::runtime_error("DXGI adapter description failed");
            if (desc.VendorId == 0x10de &&
                std::wstring(desc.Description) == L"NVIDIA GeForce RTX 5090") {
                adapter = candidate;
                break;
            }
        }
        if (!adapter) throw std::runtime_error("Validated RTX 5090 adapter not found");
        D3D_FEATURE_LEVEL level{};
        if (FAILED(D3D11CreateDevice(adapter.Get(), D3D_DRIVER_TYPE_UNKNOWN, nullptr,
            0, nullptr, 0, D3D11_SDK_VERSION, &device, &level, &context)))
            throw std::runtime_error("D3D11 device creation failed");
        D3D11_TEXTURE2D_DESC desc{};
        desc.Width = width;
        desc.Height = height;
        desc.MipLevels = 1;
        desc.ArraySize = 1;
        desc.Format = DXGI_FORMAT_B8G8R8A8_UNORM;
        desc.SampleDesc.Count = 1;
        desc.Usage = D3D11_USAGE_DEFAULT;
        desc.BindFlags = D3D11_BIND_SHADER_RESOURCE;
        if (FAILED(device->CreateTexture2D(&desc, nullptr, &input)))
            throw std::runtime_error("NVOF input texture creation failed");
        bgra.resize(static_cast<size_t>(width) * height * 4);
    }

    void check() const {
        if (owner != std::this_thread::get_id())
            throw std::runtime_error("NVOF probe used from another thread");
    }
};

template<class Clock = std::chrono::steady_clock>
uint64_t elapsed_us(typename Clock::time_point start) {
    return static_cast<uint64_t>(
        std::chrono::duration_cast<std::chrono::microseconds>(Clock::now() - start).count());
}
}  // namespace

extern "C" __declspec(dllexport) const char* nvof_probe_error() {
    return last_error.c_str();
}

extern "C" __declspec(dllexport) int nvof_probe_available() {
    return NvofDriverApiAvailable() ? 1 : 0;
}

extern "C" __declspec(dllexport) void* nvof_probe_create(int width, int height) {
    try {
        last_error.clear();
        return new Probe(static_cast<uint32_t>(width), static_cast<uint32_t>(height));
    } catch (const std::exception& error) {
        last_error = error.what();
        return nullptr;
    }
}

extern "C" __declspec(dllexport) int nvof_probe_prepare(void* value,
    const uint8_t* rgb, int reset, int16_t* flow, size_t flow_values,
    ProbeTiming* timing) {
    try {
        auto* probe = static_cast<Probe*>(value);
        if (!probe || !rgb || !flow || !timing || (reset != 0 && reset != 1))
            throw std::runtime_error("Invalid NVOF prepare descriptor");
        probe->check();
        const size_t cells = static_cast<size_t>((probe->width + 1) / 2) *
            ((probe->height + 1) / 2);
        if (flow_values < cells * 2)
            throw std::runtime_error("NVOF output buffer is too small");

        const auto bgra_start = std::chrono::steady_clock::now();
        const size_t pixels = static_cast<size_t>(probe->width) * probe->height;
        for (size_t i = 0; i < pixels; ++i) {
            probe->bgra[i * 4] = rgb[i * 3 + 2];
            probe->bgra[i * 4 + 1] = rgb[i * 3 + 1];
            probe->bgra[i * 4 + 2] = rgb[i * 3];
            probe->bgra[i * 4 + 3] = 255;
        }
        timing->bgra_us = elapsed_us(bgra_start);

        const auto upload_start = std::chrono::steady_clock::now();
        probe->context->UpdateSubresource(probe->input.Get(), 0, nullptr,
            probe->bgra.data(), probe->width * 4, 0);
        timing->upload_us = elapsed_us(upload_start);

        NvofFlowFrame result;
        std::string error;
        const auto nvof_start = std::chrono::steady_clock::now();
        if (!NvofPrepareFrame(probe->adapter.Get(), probe->device.Get(),
            probe->context.Get(), probe->input.Get(), probe->width, probe->height,
            reset != 0, result, error, false))
            throw std::runtime_error(error);
        timing->nvof_us = elapsed_us(nvof_start);
        timing->flow_width = result.width;
        timing->flow_height = result.height;
        timing->grid = result.grid;
        timing->has_flow = result.has_flow ? 1u : 0u;
        if (result.has_flow) {
            if (result.width != (probe->width + 1) / 2 ||
                result.height != (probe->height + 1) / 2 || result.grid != 2 ||
                result.xy.size() != cells * 2)
                throw std::runtime_error("Unexpected NVOF flow shape");
            std::memcpy(flow, result.xy.data(), result.xy.size() * sizeof(int16_t));
        } else {
            std::memset(flow, 0, cells * 2 * sizeof(int16_t));
        }
        return 1;
    } catch (const std::exception& error) {
        last_error = error.what();
        return 0;
    }
}

extern "C" __declspec(dllexport) int nvof_probe_destroy(void* value) {
    try {
        auto* probe = static_cast<Probe*>(value);
        if (!probe) return 1;
        probe->check();
        NvofShutdown();
        delete probe;
        return 1;
    } catch (const std::exception& error) {
        last_error = error.what();
        return 0;
    }
}
