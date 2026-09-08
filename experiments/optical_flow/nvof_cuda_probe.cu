// Isolated CUDA-interface NVOF diagnostic using NVIDIA's public SDK headers.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>

#include <cuda.h>
#include <cuda_runtime.h>
#include <nvOpticalFlowCuda.h>

#include <chrono>
#include <cstdint>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {
thread_local std::string last_error;

struct ProbeTiming {
    uint64_t pack_us;
    uint64_t upload_us;
    uint64_t nvof_us;
    uint32_t flow_width;
    uint32_t flow_height;
    uint32_t grid;
    uint32_t has_flow;
};

struct WarpTiming {
    uint64_t pack_us;
    uint64_t upload_us;
    uint64_t nvof_us;
    uint64_t warp_us;
    uint64_t readback_us;
    uint32_t valid_pixels;
};

__global__ void warp_depth_kernel(
    const float* previous, float* warped, uint8_t* valid,
    const uint8_t* flow_base, size_t flow_pitch, uint32_t width,
    uint32_t height, uint32_t flow_width, uint32_t flow_height) {
    const uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
    const uint32_t pixels = width * height;
    if (index >= pixels) return;
    const uint32_t x = index % width;
    const uint32_t y = index / width;
    const uint32_t flow_x = min(
        static_cast<uint32_t>((static_cast<uint64_t>(x) * flow_width) / width),
        flow_width - 1);
    const uint32_t flow_y = min(
        static_cast<uint32_t>((static_cast<uint64_t>(y) * flow_height) / height),
        flow_height - 1);
    const auto* row = reinterpret_cast<const short2*>(flow_base + flow_y * flow_pitch);
    const short2 vector = row[flow_x];
    const float source_x = static_cast<float>(x) + static_cast<float>(vector.x) / 32.0f;
    const float source_y = static_cast<float>(y) + static_cast<float>(vector.y) / 32.0f;
    const bool inside = source_x >= 1.0f && source_x < static_cast<float>(width - 2) &&
                        source_y >= 1.0f && source_y < static_cast<float>(height - 2);
    valid[index] = inside ? 1 : 0;
    if (!inside) {
        warped[index] = 0.0f;
        return;
    }
    const int x0 = static_cast<int>(floorf(source_x));
    const int y0 = static_cast<int>(floorf(source_y));
    const float tx = source_x - static_cast<float>(x0);
    const float ty = source_y - static_cast<float>(y0);
    const float top = previous[y0 * width + x0] * (1.0f - tx) +
                      previous[y0 * width + x0 + 1] * tx;
    const float bottom = previous[(y0 + 1) * width + x0] * (1.0f - tx) +
                         previous[(y0 + 1) * width + x0 + 1] * tx;
    const float value = top * (1.0f - ty) + bottom * ty;
    if (!isfinite(value)) {
        valid[index] = 0;
        warped[index] = 0.0f;
        return;
    }
    warped[index] = value;
}

using CreateApi = NV_OF_STATUS(NVOFAPI*)(uint32_t, NV_OF_CUDA_API_FUNCTION_LIST*);

void check_cuda(cudaError_t status, const char* operation) {
    if (status != cudaSuccess)
        throw std::runtime_error(std::string(operation) + ": " + cudaGetErrorString(status));
}

void check_of(NV_OF_STATUS status, const char* operation) {
    if (status != NV_OF_SUCCESS)
        throw std::runtime_error(std::string(operation) + ": status " +
                                 std::to_string(static_cast<int>(status)));
}

template<class Clock = std::chrono::steady_clock>
uint64_t elapsed_us(typename Clock::time_point start) {
    return static_cast<uint64_t>(
        std::chrono::duration_cast<std::chrono::microseconds>(Clock::now() - start).count());
}

struct Probe {
    enum class Mode { unused, host_flow, device_warp };
    uint32_t width = 0;
    uint32_t height = 0;
    uint32_t flow_width = 0;
    uint32_t flow_height = 0;
    HMODULE library = nullptr;
    NV_OF_CUDA_API_FUNCTION_LIST api{};
    NvOFHandle session = nullptr;
    NvOFGPUBufferHandle inputs[2]{};
    NvOFGPUBufferHandle output = nullptr;
    CUdeviceptr input_ptrs[2]{};
    CUdeviceptr output_ptr = 0;
    size_t input_pitch = 0;
    size_t output_pitch = 0;
    cudaStream_t input_stream = nullptr;
    cudaStream_t output_stream = nullptr;
    cudaEvent_t source_ready = nullptr;
    float* depth[2]{};
    uint8_t* validity = nullptr;
    std::vector<uint8_t> rgba;
    int current = 0;
    int active_depth = 0;
    bool primed = false;
    bool warp_pending = false;
    bool poisoned = false;
    uint64_t last_generation = 0;
    uint64_t pending_generation = 0;
    Mode mode = Mode::unused;
    std::thread::id owner = std::this_thread::get_id();

    ~Probe() { close(); }

    void close() noexcept {
        if (input_stream) cudaStreamSynchronize(input_stream);
        if (output_stream) cudaStreamSynchronize(output_stream);
        if (api.nvOFDestroyGPUBufferCuda) {
            for (auto& input : inputs) {
                if (input) api.nvOFDestroyGPUBufferCuda(input);
                input = nullptr;
            }
            if (output) api.nvOFDestroyGPUBufferCuda(output);
            output = nullptr;
        }
        if (session && api.nvOFDestroy) api.nvOFDestroy(session);
        session = nullptr;
        for (auto& value : depth) {
            if (value) cudaFree(value);
            value = nullptr;
        }
        if (validity) cudaFree(validity);
        validity = nullptr;
        if (source_ready) cudaEventDestroy(source_ready);
        source_ready = nullptr;
        if (input_stream) cudaStreamDestroy(input_stream);
        if (output_stream) cudaStreamDestroy(output_stream);
        input_stream = output_stream = nullptr;
        if (library) FreeLibrary(library);
        library = nullptr;
    }

    void check_owner() const {
        if (owner != std::this_thread::get_id())
            throw std::runtime_error("NVOF probe used from another thread");
    }

    void init(uint32_t w, uint32_t h) {
        if (w < 16 || h < 16 || w > 4096 || h > 2160)
            throw std::runtime_error("Invalid NVOF probe dimensions");
        width = w;
        height = h;
        flow_width = (w + 1) / 2;
        flow_height = (h + 1) / 2;

        check_cuda(cudaSetDevice(0), "cudaSetDevice");
        cudaDeviceProp properties{};
        check_cuda(cudaGetDeviceProperties(&properties, 0), "cudaGetDeviceProperties");
        if (std::string(properties.name) != "NVIDIA GeForce RTX 5090")
            throw std::runtime_error("Validated RTX 5090 CUDA device not found");
        check_cuda(cudaFree(nullptr), "CUDA context initialization");
        CUcontext context = nullptr;
        if (cuCtxGetCurrent(&context) != CUDA_SUCCESS || !context)
            throw std::runtime_error("CUDA primary context is unavailable");

        library = LoadLibraryW(L"nvofapi64.dll");
        if (!library) throw std::runtime_error("nvofapi64.dll is unavailable");
        auto create_api = reinterpret_cast<CreateApi>(
            GetProcAddress(library, "NvOFAPICreateInstanceCuda"));
        if (!create_api) throw std::runtime_error("CUDA NVOF entry point is unavailable");
        check_of(create_api(NV_OF_API_VERSION, &api), "NvOFAPICreateInstanceCuda");
        if (!api.nvCreateOpticalFlowCuda || !api.nvOFInit ||
            !api.nvOFCreateGPUBufferCuda || !api.nvOFGPUBufferGetCUdeviceptr ||
            !api.nvOFGPUBufferGetStrideInfo || !api.nvOFSetIOCudaStreams ||
            !api.nvOFExecute || !api.nvOFDestroyGPUBufferCuda || !api.nvOFDestroy)
            throw std::runtime_error("CUDA NVOF function table is incomplete");

        check_of(api.nvCreateOpticalFlowCuda(context, &session),
                 "NvCreateOpticalFlowCuda");
        check_cuda(cudaStreamCreateWithFlags(&input_stream, cudaStreamNonBlocking),
                   "input stream creation");
        check_cuda(cudaStreamCreateWithFlags(&output_stream, cudaStreamNonBlocking),
                   "output stream creation");
        check_of(api.nvOFSetIOCudaStreams(session, reinterpret_cast<CUstream>(input_stream),
                                          reinterpret_cast<CUstream>(output_stream)),
                 "NvOFSetIOCudaStreams");

        NV_OF_INIT_PARAMS init_params{};
        init_params.width = width;
        init_params.height = height;
        init_params.outGridSize = NV_OF_OUTPUT_VECTOR_GRID_SIZE_2;
        init_params.hintGridSize = NV_OF_HINT_VECTOR_GRID_SIZE_2;
        init_params.mode = NV_OF_MODE_OPTICALFLOW;
        init_params.perfLevel = NV_OF_PERF_LEVEL_FAST;
        check_of(api.nvOFInit(session, &init_params), "NvOFInit");

        NV_OF_BUFFER_DESCRIPTOR input_desc{};
        input_desc.width = width;
        input_desc.height = height;
        input_desc.bufferUsage = NV_OF_BUFFER_USAGE_INPUT;
        input_desc.bufferFormat = NV_OF_BUFFER_FORMAT_ABGR8;
        for (auto& input : inputs)
            check_of(api.nvOFCreateGPUBufferCuda(session, &input_desc,
                                                 NV_OF_CUDA_BUFFER_TYPE_CUDEVICEPTR,
                                                 &input),
                     "input buffer creation");

        NV_OF_BUFFER_DESCRIPTOR output_desc{};
        output_desc.width = flow_width;
        output_desc.height = flow_height;
        output_desc.bufferUsage = NV_OF_BUFFER_USAGE_OUTPUT;
        output_desc.bufferFormat = NV_OF_BUFFER_FORMAT_SHORT2;
        check_of(api.nvOFCreateGPUBufferCuda(session, &output_desc,
                                             NV_OF_CUDA_BUFFER_TYPE_CUDEVICEPTR,
                                             &output),
                 "output buffer creation");

        for (int index = 0; index < 2; ++index) {
            input_ptrs[index] = api.nvOFGPUBufferGetCUdeviceptr(inputs[index]);
            if (!input_ptrs[index]) throw std::runtime_error("Null NVOF input pointer");
        }
        output_ptr = api.nvOFGPUBufferGetCUdeviceptr(output);
        if (!output_ptr) throw std::runtime_error("Null NVOF output pointer");

        NV_OF_CUDA_BUFFER_STRIDE_INFO input_stride{};
        NV_OF_CUDA_BUFFER_STRIDE_INFO output_stride{};
        check_of(api.nvOFGPUBufferGetStrideInfo(inputs[0], &input_stride),
                 "input stride query");
        check_of(api.nvOFGPUBufferGetStrideInfo(output, &output_stride),
                 "output stride query");
        if (input_stride.numPlanes != 1 || output_stride.numPlanes != 1)
            throw std::runtime_error("Unexpected NVOF plane count");
        input_pitch = input_stride.strideInfo[0].strideXInBytes;
        output_pitch = output_stride.strideInfo[0].strideXInBytes;
        if (input_pitch < static_cast<size_t>(width) * 4 ||
            output_pitch < static_cast<size_t>(flow_width) * sizeof(NV_OF_FLOW_VECTOR))
            throw std::runtime_error(
                "Unexpected NVOF buffer pitch: input x=" +
                std::to_string(input_stride.strideInfo[0].strideXInBytes) +
                " y=" + std::to_string(input_stride.strideInfo[0].strideYInBytes) +
                " output x=" + std::to_string(output_stride.strideInfo[0].strideXInBytes) +
                " y=" + std::to_string(output_stride.strideInfo[0].strideYInBytes));
        const size_t pixels = static_cast<size_t>(width) * height;
        check_cuda(cudaMalloc(reinterpret_cast<void**>(&depth[0]), pixels * sizeof(float)),
                   "first depth buffer allocation");
        check_cuda(cudaMalloc(reinterpret_cast<void**>(&depth[1]), pixels * sizeof(float)),
                   "second depth buffer allocation");
        check_cuda(cudaMalloc(reinterpret_cast<void**>(&validity), pixels),
                   "validity buffer allocation");
        check_cuda(cudaEventCreateWithFlags(&source_ready, cudaEventDisableTiming),
                   "source event creation");
        rgba.resize(static_cast<size_t>(width) * height * 4);
    }

    uint64_t pack_rgb(const uint8_t* rgb) {
        const auto start = std::chrono::steady_clock::now();
        const size_t pixels = static_cast<size_t>(width) * height;
        for (size_t i = 0; i < pixels; ++i) {
            rgba[i * 4] = rgb[i * 3];
            rgba[i * 4 + 1] = rgb[i * 3 + 1];
            rgba[i * 4 + 2] = rgb[i * 3 + 2];
            rgba[i * 4 + 3] = 255;
        }
        return elapsed_us(start);
    }

    uint64_t upload_current() {
        const auto start = std::chrono::steady_clock::now();
        check_cuda(cudaMemcpy2DAsync(
                       reinterpret_cast<void*>(input_ptrs[current]), input_pitch,
                       rgba.data(), width * 4, width * 4, height,
                       cudaMemcpyHostToDevice, input_stream),
                   "NVOF input upload");
        check_cuda(cudaStreamSynchronize(input_stream), "NVOF input synchronization");
        return elapsed_us(start);
    }
};
}  // namespace

extern "C" __declspec(dllexport) const char* nvof_probe_error() {
    return last_error.c_str();
}

extern "C" __declspec(dllexport) int nvof_probe_available() {
    HMODULE library = LoadLibraryW(L"nvofapi64.dll");
    if (!library) return 0;
    const bool available =
        GetProcAddress(library, "NvOFAPICreateInstanceCuda") != nullptr;
    FreeLibrary(library);
    return available ? 1 : 0;
}

extern "C" __declspec(dllexport) void* nvof_probe_create(int width, int height) {
    try {
        last_error.clear();
        auto probe = std::make_unique<Probe>();
        probe->init(static_cast<uint32_t>(width), static_cast<uint32_t>(height));
        return probe.release();
    } catch (const std::exception& error) {
        last_error = error.what();
        return nullptr;
    }
}

extern "C" __declspec(dllexport) int nvof_probe_prepare(
    void* value, const uint8_t* rgb, int reset, int16_t* flow,
    size_t flow_values, ProbeTiming* timing) {
    try {
        auto* probe = static_cast<Probe*>(value);
        if (!probe || !rgb || !flow || !timing || (reset != 0 && reset != 1))
            throw std::runtime_error("Invalid NVOF prepare descriptor");
        probe->check_owner();
        if (probe->poisoned) throw std::runtime_error("NVOF probe is poisoned");
        if (probe->mode == Probe::Mode::unused) probe->mode = Probe::Mode::host_flow;
        if (probe->mode != Probe::Mode::host_flow)
            throw std::runtime_error("NVOF probe mode cannot be changed");
        const size_t cells = static_cast<size_t>(probe->flow_width) * probe->flow_height;
        if (flow_values < cells * 2)
            throw std::runtime_error("NVOF output buffer is too small");
        *timing = ProbeTiming{};

        if (reset) {
            probe->current = 0;
            probe->primed = false;
        }
        timing->pack_us = probe->pack_rgb(rgb);
        timing->upload_us = probe->upload_current();

        timing->grid = 2;
        if (!probe->primed) {
            probe->primed = true;
            probe->current ^= 1;
            std::memset(flow, 0, cells * 2 * sizeof(int16_t));
            return 1;
        }

        NV_OF_EXECUTE_INPUT_PARAMS input{};
        NV_OF_EXECUTE_OUTPUT_PARAMS output{};
        input.inputFrame = probe->inputs[probe->current];
        input.referenceFrame = probe->inputs[probe->current ^ 1];
        input.disableTemporalHints = NV_OF_TRUE;
        output.outputBuffer = probe->output;
        const auto nvof_start = std::chrono::steady_clock::now();
        check_of(probe->api.nvOFExecute(probe->session, &input, &output), "NvOFExecute");
        check_cuda(cudaMemcpy2DAsync(
                       flow, probe->flow_width * sizeof(NV_OF_FLOW_VECTOR),
                       reinterpret_cast<void*>(probe->output_ptr), probe->output_pitch,
                       probe->flow_width * sizeof(NV_OF_FLOW_VECTOR), probe->flow_height,
                       cudaMemcpyDeviceToHost, probe->output_stream),
                   "NVOF flow readback");
        check_cuda(cudaStreamSynchronize(probe->output_stream),
                   "NVOF output synchronization");
        timing->nvof_us = elapsed_us(nvof_start);
        timing->flow_width = probe->flow_width;
        timing->flow_height = probe->flow_height;
        timing->has_flow = 1;
        probe->current ^= 1;
        return 1;
    } catch (const std::exception& error) {
        last_error = error.what();
        return 0;
    }
}

extern "C" __declspec(dllexport) unsigned long long nvof_probe_stream(void* value) {
    try {
        auto* probe = static_cast<Probe*>(value);
        if (!probe) throw std::runtime_error("Null NVOF probe");
        probe->check_owner();
        if (probe->poisoned) throw std::runtime_error("NVOF probe is poisoned");
        return reinterpret_cast<unsigned long long>(probe->output_stream);
    } catch (const std::exception& error) {
        last_error = error.what();
        return 0;
    }
}

extern "C" __declspec(dllexport) int nvof_probe_seed_device(
    void* value, const uint8_t* rgb, const float* source_depth,
    unsigned long long source_stream, unsigned long long generation,
    float* diagnostic_depth, unsigned long long* output_pointer,
    WarpTiming* timing) {
    auto* probe = static_cast<Probe*>(value);
    try {
        if (!probe || !rgb || !source_depth || !generation || !output_pointer ||
            !timing)
            throw std::runtime_error("Invalid NVOF seed descriptor");
        probe->check_owner();
        if (probe->poisoned) throw std::runtime_error("NVOF probe is poisoned");
        if (probe->mode == Probe::Mode::unused) probe->mode = Probe::Mode::device_warp;
        if (probe->mode != Probe::Mode::device_warp)
            throw std::runtime_error("NVOF probe mode cannot be changed");
        if (probe->warp_pending)
            throw std::runtime_error("Complete the pending NVOF warp before reseeding");
        if (generation <= probe->last_generation)
            throw std::runtime_error("NVOF seed generation is stale");
        *timing = WarpTiming{};
        *output_pointer = 0;
        probe->current = 0;
        probe->active_depth = 0;
        probe->primed = false;
        timing->pack_us = probe->pack_rgb(rgb);
        timing->upload_us = probe->upload_current();

        const auto copy_start = std::chrono::steady_clock::now();
        auto producer = reinterpret_cast<cudaStream_t>(source_stream);
        check_cuda(cudaEventRecord(probe->source_ready, producer),
                   "oVDA source event record");
        check_cuda(cudaStreamWaitEvent(probe->output_stream, probe->source_ready, 0),
                   "NVOF seed wait");
        const size_t depth_bytes = static_cast<size_t>(probe->width) * probe->height *
                                   sizeof(float);
        check_cuda(cudaMemcpyAsync(probe->depth[0], source_depth, depth_bytes,
                                   cudaMemcpyDeviceToDevice, probe->output_stream),
                   "NVOF seed depth copy");
        check_cuda(cudaStreamSynchronize(probe->output_stream),
                   "NVOF seed synchronization");
        timing->warp_us = elapsed_us(copy_start);
        if (diagnostic_depth) {
            const auto readback_start = std::chrono::steady_clock::now();
            check_cuda(cudaMemcpyAsync(diagnostic_depth, probe->depth[0], depth_bytes,
                                       cudaMemcpyDeviceToHost, probe->output_stream),
                       "NVOF seed readback");
            check_cuda(cudaStreamSynchronize(probe->output_stream),
                       "NVOF seed readback synchronization");
            timing->readback_us = elapsed_us(readback_start);
        }
        timing->valid_pixels = probe->width * probe->height;
        probe->current = 1;
        probe->primed = true;
        probe->last_generation = generation;
        *output_pointer = reinterpret_cast<unsigned long long>(probe->depth[0]);
        return 1;
    } catch (const std::exception& error) {
        if (probe) probe->poisoned = true;
        last_error = error.what();
        return 0;
    }
}

extern "C" __declspec(dllexport) int nvof_probe_warp_device(
    void* value, const uint8_t* rgb, unsigned long long generation,
    int16_t* diagnostic_flow, size_t flow_values,
    float* diagnostic_depth, size_t depth_values,
    uint8_t* diagnostic_valid, size_t valid_values,
    unsigned long long* output_pointer, WarpTiming* timing) {
    auto* probe = static_cast<Probe*>(value);
    try {
        if (!probe || !rgb || !generation || !output_pointer || !timing)
            throw std::runtime_error("Invalid NVOF warp descriptor");
        probe->check_owner();
        if (probe->poisoned) throw std::runtime_error("NVOF probe is poisoned");
        if (probe->mode != Probe::Mode::device_warp || !probe->primed)
            throw std::runtime_error("Seed NVOF depth before warping");
        if (probe->warp_pending)
            throw std::runtime_error("Complete the pending NVOF warp before reuse");
        if (generation != probe->last_generation + 1)
            throw std::runtime_error("NVOF warp generation is not consecutive");
        const size_t cells = static_cast<size_t>(probe->flow_width) * probe->flow_height;
        const size_t pixels = static_cast<size_t>(probe->width) * probe->height;
        if ((diagnostic_flow && flow_values < cells * 2) ||
            (diagnostic_depth && depth_values < pixels) ||
            (diagnostic_valid && valid_values < pixels))
            throw std::runtime_error("NVOF warp diagnostic buffer is too small");
        *timing = WarpTiming{};
        *output_pointer = 0;
        timing->pack_us = probe->pack_rgb(rgb);
        timing->upload_us = probe->upload_current();

        NV_OF_EXECUTE_INPUT_PARAMS input{};
        NV_OF_EXECUTE_OUTPUT_PARAMS output{};
        input.inputFrame = probe->inputs[probe->current];
        input.referenceFrame = probe->inputs[probe->current ^ 1];
        input.disableTemporalHints = NV_OF_TRUE;
        output.outputBuffer = probe->output;
        const auto nvof_start = std::chrono::steady_clock::now();
        check_of(probe->api.nvOFExecute(probe->session, &input, &output),
                 "NvOFExecute for depth warp");
        check_cuda(cudaStreamSynchronize(probe->output_stream),
                   "NVOF depth-warp flow synchronization");
        timing->nvof_us = elapsed_us(nvof_start);

        const auto warp_start = std::chrono::steady_clock::now();
        const int target = 1 - probe->active_depth;
        const int blocks = static_cast<int>((pixels + 255) / 256);
        warp_depth_kernel<<<blocks, 256, 0, probe->output_stream>>>(
            probe->depth[probe->active_depth], probe->depth[target], probe->validity,
            reinterpret_cast<const uint8_t*>(probe->output_ptr), probe->output_pitch,
            probe->width, probe->height, probe->flow_width, probe->flow_height);
        check_cuda(cudaGetLastError(), "NVOF depth-warp kernel launch");
        check_cuda(cudaStreamSynchronize(probe->output_stream),
                   "NVOF depth-warp synchronization");
        timing->warp_us = elapsed_us(warp_start);

        if (diagnostic_flow || diagnostic_depth || diagnostic_valid) {
            const auto readback_start = std::chrono::steady_clock::now();
            if (diagnostic_flow)
                check_cuda(cudaMemcpy2DAsync(
                               diagnostic_flow,
                               probe->flow_width * sizeof(NV_OF_FLOW_VECTOR),
                               reinterpret_cast<void*>(probe->output_ptr),
                               probe->output_pitch,
                               probe->flow_width * sizeof(NV_OF_FLOW_VECTOR),
                               probe->flow_height, cudaMemcpyDeviceToHost,
                               probe->output_stream),
                           "NVOF warp flow readback");
            if (diagnostic_depth)
                check_cuda(cudaMemcpyAsync(diagnostic_depth, probe->depth[target],
                                           pixels * sizeof(float),
                                           cudaMemcpyDeviceToHost,
                                           probe->output_stream),
                           "NVOF warped-depth readback");
            if (diagnostic_valid)
                check_cuda(cudaMemcpyAsync(diagnostic_valid, probe->validity, pixels,
                                           cudaMemcpyDeviceToHost,
                                           probe->output_stream),
                           "NVOF validity readback");
            check_cuda(cudaStreamSynchronize(probe->output_stream),
                       "NVOF warp diagnostic synchronization");
            timing->readback_us = elapsed_us(readback_start);
            if (diagnostic_valid) {
                uint32_t count = 0;
                for (size_t i = 0; i < pixels; ++i) count += diagnostic_valid[i] != 0;
                timing->valid_pixels = count;
            }
        }
        probe->warp_pending = true;
        probe->pending_generation = generation;
        *output_pointer = reinterpret_cast<unsigned long long>(probe->depth[target]);
        return 1;
    } catch (const std::exception& error) {
        if (probe) probe->poisoned = true;
        last_error = error.what();
        return 0;
    }
}

extern "C" __declspec(dllexport) int nvof_probe_complete_warp(
    void* value, unsigned long long generation, int retain) {
    auto* probe = static_cast<Probe*>(value);
    try {
        if (!probe || (retain != 0 && retain != 1))
            throw std::runtime_error("Invalid NVOF completion descriptor");
        probe->check_owner();
        if (probe->poisoned) throw std::runtime_error("NVOF probe is poisoned");
        if (!probe->warp_pending || generation != probe->pending_generation)
            throw std::runtime_error("NVOF warp token expired");
        check_cuda(cudaStreamSynchronize(probe->output_stream),
                   "NVOF completion synchronization");
        probe->current ^= 1;
        if (retain) {
            probe->active_depth = 1 - probe->active_depth;
        } else {
            probe->primed = false;
        }
        probe->last_generation = generation;
        probe->pending_generation = 0;
        probe->warp_pending = false;
        return 1;
    } catch (const std::exception& error) {
        if (probe) probe->poisoned = true;
        last_error = error.what();
        return 0;
    }
}

extern "C" __declspec(dllexport) int nvof_probe_destroy(void* value) {
    try {
        auto* probe = static_cast<Probe*>(value);
        if (!probe) return 1;
        probe->check_owner();
        delete probe;
        return 1;
    } catch (const std::exception& error) {
        last_error = error.what();
        return 0;
    }
}
