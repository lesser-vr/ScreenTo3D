// Isolated SDK experiment. No capture, app backend or ambient plugin discovery.
#include <windows.h>
#include <cuda_runtime_api.h>
#include "nvVideoEffects.h"
#include "nvVFXVideoFrameGeneration.h"
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;
using Clock = std::chrono::steady_clock;
char* g_nvVFXSDKPath = nullptr;
static const char* stage = "setup";
static void check(NvCV_Status s) {
    if (s != NVCV_SUCCESS) throw std::runtime_error("NvCV status " + std::to_string(s));
}
static void cu(cudaError_t s) {
    if (s != cudaSuccess) throw std::runtime_error(cudaGetErrorString(s));
}
static double elapsed(Clock::time_point start) {
    return std::chrono::duration<double, std::milli>(Clock::now() - start).count();
}
static std::vector<unsigned char> read(const fs::path& p, size_t n) {
    if (fs::file_size(p) != n) throw std::runtime_error("Input byte size mismatch");
    std::vector<unsigned char> v(n);
    std::ifstream f(p, std::ios::binary);
    if (!f.read(reinterpret_cast<char*>(v.data()), n)) throw std::runtime_error("Read failed");
    return v;
}
struct Session {
    // Construction happens only after trusted DLL directories have been set.
    NvCVImage previous, current, output;
    NvVFX_Handle effect = nullptr;
    cudaStream_t stream = nullptr;
    cudaEvent_t begin = nullptr, end = nullptr;
    ~Session() {
        if (stream) cudaStreamSynchronize(stream);
        if (effect) NvVFX_DestroyEffect(effect);
        NvCVImage_Dealloc(&output);
        NvCVImage_Dealloc(&current);
        NvCVImage_Dealloc(&previous);
        if (begin) cudaEventDestroy(begin);
        if (end) cudaEventDestroy(end);
        if (stream) cudaStreamDestroy(stream);
        // NvCVImage destructors accept the cleared images (SDK dealloc is idempotent).
    }
    void upload(NvCVImage& image, const std::vector<unsigned char>& v, unsigned w, unsigned h) {
        cu(cudaMemcpy2DAsync(image.pixels, image.pitch, v.data(), w * 4,
                            w * 4, h, cudaMemcpyHostToDevice, stream));
        cu(cudaStreamSynchronize(stream));
    }
    void bind(bool cut) {
        check(NvVFX_SetImage(effect, NVVFX_INPUT_IMAGE_0, &previous));
        check(NvVFX_SetImage(effect, NVVFX_INPUT_IMAGE_1, &current));
        check(NvVFX_SetU32(effect, NVVFXVIDEOFRAMEGENERATION_SHOT_CHANGE, cut ? 1 : 0));
        check(NvVFX_SetU32(effect, NVVFXVIDEOFRAMEGENERATION_FRAME_INDEX, 1));
    }
    void run() { check(NvVFX_Run(effect, 0)); }
    void save(const fs::path& path, unsigned w, unsigned h) {
        std::vector<unsigned char> v(size_t(w) * h * 4);
        cu(cudaMemcpy2DAsync(v.data(), w * 4, output.pixels, output.pitch, w * 4,
                            h, cudaMemcpyDeviceToHost, stream));
        cu(cudaStreamSynchronize(stream));
        std::ofstream f(path, std::ios::binary);
        f.write(reinterpret_cast<const char*>(v.data()), v.size());
        if (!f) throw std::runtime_error("Output write failed");
    }
};
int main(int argc, char** argv) {
    // sdk, raw input directory, NEW output directory, width, height, mode, auto-cut
    if (argc != 8) return 2;
    fs::path destination = fs::absolute(argv[3]);
    if (fs::exists(destination)) return 2;
    fs::create_directories(destination);
    std::ofstream report(destination / "result.json");
    try {
        unsigned w = std::stoul(argv[4]), h = std::stoul(argv[5]);
        unsigned mode = std::stoul(argv[6]), autoCut = std::stoul(argv[7]);
        if (w < 64 || w > 7680 || h < 64 || h > 2160 || mode > 2 || autoCut > 1)
            throw std::runtime_error("Invalid bounded probe arguments");
        auto sdk = fs::canonical(argv[1]);
        auto bin = sdk / "bin";
        auto feature = sdk / "features/nvvfxvideoframegeneration/bin";
        if (!SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_SYSTEM32 | LOAD_LIBRARY_SEARCH_USER_DIRS)
            || !AddDllDirectory(bin.c_str()) || !AddDllDirectory(feature.c_str()))
            throw std::runtime_error("DLL directory setup failed");
        SetEnvironmentVariableW(L"NV_VIDEO_EFFECTS_PATH", bin.c_str());
        // Preload only SDK-owned, absolute module paths. Handles live until process exit.
        for (auto p : {bin / "NVVideoEffects.dll", bin / "NVCVImage.dll", feature / "nvVFXVideoFrameGeneration.dll"}) {
            if (!LoadLibraryExW(p.c_str(), nullptr, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS))
                throw std::runtime_error("SDK DLL load failed " + std::to_string(GetLastError()));
        }
        double loadMs = 0;
        std::vector<double> gpuMs, wallMs;
        {
            Session s;
            stage = "create";
            cu(cudaSetDevice(0));
            cu(cudaStreamCreateWithFlags(&s.stream, cudaStreamNonBlocking));
            cu(cudaEventCreate(&s.begin)); cu(cudaEventCreate(&s.end));
            check(NvVFX_CreateEffect(NVVFX_FX_VIDEO_FRAME_GENERATION, &s.effect));
            check(NvVFX_SetCudaStream(s.effect, NVVFX_CUDA_STREAM, s.stream));
            check(NvVFX_SetU32(s.effect, NVVFX_INPUT_WIDTH, w));
            check(NvVFX_SetU32(s.effect, NVVFX_INPUT_HEIGHT, h));
            check(NvVFX_SetU32(s.effect, NVVFXVIDEOFRAMEGENERATION_MODE, mode));
            check(NvVFX_SetU32(s.effect, NVVFXVIDEOFRAMEGENERATION_AUTOMATIC_SHOT_CHANGE_DETECTION_ENABLED, autoCut));
            stage = "load";
            auto start = Clock::now(); check(NvVFX_Load(s.effect));
            cu(cudaStreamSynchronize(s.stream)); loadMs = elapsed(start);
            stage = "allocate";
            for (auto image : {&s.previous, &s.current, &s.output})
                check(NvCVImage_Alloc(image, w, h, NVCV_RGBA, NVCV_U8, NVCV_INTERLEAVED, NVCV_GPU, 32));
            check(NvVFX_SetImage(s.effect, NVVFX_OUTPUT_IMAGE, &s.output));
            check(NvVFX_SetU32(s.effect, NVVFXVIDEOFRAMEGENERATION_FRAME_MULTIPLIER, 2));
            const fs::path input(argv[2]);
            for (const auto name : {"identity", "translation", "cut", "after_cut"}) {
                stage = name;
                auto source = input / (std::string(name) == "after_cut" ? "translation" : name);
                s.upload(s.previous, read(source / "previous.rgba", size_t(w) * h * 4), w, h);
                s.upload(s.current, read(source / "current.rgba", size_t(w) * h * 4), w, h);
                s.bind(std::string(name) == "cut" && !autoCut); s.run();
                s.save(destination / (std::string(name) + ".rgba"), w, h);
            }
            // Translation is now bound. Rebind on EACH repeat to avoid cached-pair timings.
            stage = "warmup";
            for (int i = 0; i < 5; ++i) { s.bind(false); s.run(); cu(cudaStreamSynchronize(s.stream)); }
            stage = "measure";
            for (int repeat = 0; repeat < 5; ++repeat) {
                double gpuTotal = 0, wallTotal = 0;
                for (int i = 0; i < 10; ++i) {
                    auto start = Clock::now();
                    cu(cudaEventRecord(s.begin, s.stream)); s.bind(false); s.run();
                    cu(cudaEventRecord(s.end, s.stream)); cu(cudaEventSynchronize(s.end));
                    wallTotal += elapsed(start);
                    float ms = 0; cu(cudaEventElapsedTime(&ms, s.begin, s.end)); gpuTotal += ms;
                }
                gpuMs.push_back(gpuTotal / 10); wallMs.push_back(wallTotal / 10);
            }
            stage = "drain"; cu(cudaStreamSynchronize(s.stream));
        }
        // The process boundary is not proof of in-app resource-lifecycle parity.
        report << "{\"success\":true,\"load_ms\":" << loadMs << ",\"gpu_ms\":[";
        for (size_t i=0; i<gpuMs.size(); ++i) report << (i ? "," : "") << gpuMs[i];
        report << "],\"wall_ms\":[";
        for (size_t i=0; i<wallMs.size(); ++i) report << (i ? "," : "") << wallMs[i];
        report << "]}\n";
        std::cout << "completed " << w << "x" << h << " mode " << mode << "\n";
        return 0;
    } catch (const std::exception& e) {
        report << "{\"success\":false,\"stage\":\"" << stage << "\"}\n";
        std::cerr << stage << ": " << e.what() << "\n";
        return 1;
    }
}
