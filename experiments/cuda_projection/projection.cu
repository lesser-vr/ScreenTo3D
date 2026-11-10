#include <cuda_runtime.h>
#include <cmath>
#include <cstdint>
#include <initializer_list>
#include <new>

// Experimental host-to-host C API, not loaded by the production application.
__global__ void splat(const float* depth, const float* shift,
                      unsigned long long* owners, int width, int count, bool coverage) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= count) return;
    int x = i % width, row = i - x;
    double target = double(x) + double(shift[i]);
    int a = int(coverage ? floor(target) : nearbyint(target));
    int b = coverage ? int(ceil(target)) : a;
    float z = fminf(fmaxf(depth[i], 0.f), 1.f);
    auto key = ((static_cast<unsigned long long>(__fmul_rn(z, 65535.f)) + 1ULL) << 32)
               | static_cast<unsigned int>(i);
    if (a >= 0 && a < width) atomicMax(owners + row + a, key);
    if (b != a && b >= 0 && b < width) atomicMax(owners + row + b, key);
}

__device__ void copy_pixel(const unsigned char* rgb, unsigned char* output, int dst, int src) {
    for (int c = 0; c < 3; ++c) output[dst * 3 + c] = rgb[src * 3 + c];
}

__global__ void resolve(const unsigned char* rgb, const unsigned long long* owners,
                        unsigned char* output, int width, int height) {
    int y = blockIdx.x * blockDim.x + threadIdx.x;
    if (y >= height) return;
    int row = y * width, x = 0, left = -1;
    while (x < width) {
        if (owners[row + x]) {
            copy_pixel(rgb, output, row + x, int(owners[row + x] & 0xffffffffULL));
            left = x++;
            continue;
        }
        int start = x;
        while (x < width && !owners[row + x]) ++x;
        int chosen = left;
        if (left < 0 || (x < width && (owners[row + x] >> 32) < (owners[row + left] >> 32))) chosen = x;
        for (int hole = start; hole < x; ++hole) {
            int src = chosen < width ? int(owners[row + chosen] & 0xffffffffULL) : row + hole;
            copy_pixel(rgb, output, row + hole, src);
        }
    }
}

struct ProjectionContext {
    int width, height, count;
    int device = -1;
    unsigned char *d_rgb = nullptr, *d_output = nullptr;
    float *d_depth = nullptr, *d_shift = nullptr;
    unsigned long long* d_owners = nullptr;
    cudaStream_t stream = nullptr;
};

static cudaError_t release(ProjectionContext* context) {
    if (!context) return cudaSuccess;
    if (context->device < 0) { delete context; return cudaSuccess; }
    int previous = -1;
    cudaError_t result = cudaGetDevice(&previous);
    auto select = cudaSetDevice(context->device);
    if (result == cudaSuccess) result = select;
    if (context->stream) { auto e = cudaStreamSynchronize(context->stream); if (result == cudaSuccess) result = e; }
    for (void* p : {static_cast<void*>(context->d_owners), static_cast<void*>(context->d_shift),
                   static_cast<void*>(context->d_depth), static_cast<void*>(context->d_output),
                   static_cast<void*>(context->d_rgb)}) {
        if (p) { auto e = cudaFree(p); if (result == cudaSuccess) result = e; }
    }
    if (context->stream) { auto e = cudaStreamDestroy(context->stream); if (result == cudaSuccess) result = e; }
    if (previous >= 0 && previous != context->device) { auto e = cudaSetDevice(previous); if (result == cudaSuccess) result = e; }
    delete context;
    return result;
}

static int create_context(void** output, int width, int height, int fail_stage) {
    if (!output) return int(cudaErrorInvalidValue);
    *output = nullptr;
    if (width < 1 || height < 1 || width > 7680 || height > 4320)
        return int(cudaErrorInvalidValue);
    auto context = new (std::nothrow) ProjectionContext{width, height, width * height};
    if (!context) return int(cudaErrorMemoryAllocation);
    auto allocate = [&]() -> cudaError_t {
        auto device_status = cudaGetDevice(&context->device);
        if (device_status != cudaSuccess) return device_status;
        int stage = 0;
#define CHECK(call) do { cudaError_t e = (call); if (e != cudaSuccess) return e; if (++stage == fail_stage) return cudaErrorMemoryAllocation; } while (0)
        CHECK(cudaStreamCreateWithFlags(&context->stream, cudaStreamNonBlocking));
        CHECK(cudaMalloc(&context->d_rgb, size_t(context->count) * 3));
        CHECK(cudaMalloc(&context->d_output, size_t(context->count) * 3));
        CHECK(cudaMalloc(&context->d_depth, size_t(context->count) * sizeof(float)));
        CHECK(cudaMalloc(&context->d_shift, size_t(context->count) * sizeof(float)));
        CHECK(cudaMalloc(&context->d_owners, size_t(context->count) * sizeof(unsigned long long)));
        return cudaSuccess;
#undef CHECK
    };
    auto result = allocate();
    if (result != cudaSuccess) { release(context); return int(result); }
    *output = context;
    return int(cudaSuccess);
}

extern "C" __declspec(dllexport) int projection_create(void** output, int width, int height) {
#ifdef DEPTHSBS_GPU_PREVIEW
    int device = -1, driver = 0;
    cudaDeviceProp properties{};
    auto status = cudaGetDevice(&device);
    if (status != cudaSuccess) return int(status);
    status = cudaGetDeviceProperties(&properties, device);
    if (status != cudaSuccess) return int(status);
    status = cudaDriverGetVersion(&driver);
    if (status != cudaSuccess) return int(status);
#ifdef DEPTHSBS_PORTABLE_CUDA
    if (properties.major * 10 + properties.minor < 75) return int(cudaErrorInvalidDevice);
#else
    if (properties.major != 12 || properties.minor != 0) return int(cudaErrorInvalidDevice);
#endif
    if (driver < 13010) return int(cudaErrorInsufficientDriver);
#endif
    return create_context(output, width, height, 0);
}

// Fault injection only in the experimental DLL; no persistent global state.
#ifndef DEPTHSBS_GPU_PREVIEW
extern "C" __declspec(dllexport) int projection_create_injected(void** output, int width, int height, int stage) {
    if (stage < 1 || stage > 6) return int(cudaErrorInvalidValue);
    return create_context(output, width, height, stage);
}
#endif

extern "C" __declspec(dllexport) int projection_run(
    void* handle, const unsigned char* rgb, const float* depth, const float* shift,
    unsigned char* output, int coverage) {
    auto context = static_cast<ProjectionContext*>(handle);
    if (!context || !rgb || !depth || !shift || !output) return int(cudaErrorInvalidValue);
    int current_device = -1;
    auto device_status = cudaGetDevice(&current_device);
    if (device_status != cudaSuccess) return int(device_status);
    if (current_device != context->device) return int(cudaErrorInvalidDevice);
    auto run = [&]() -> cudaError_t {
#define CHECK(call) do { cudaError_t e = (call); if (e != cudaSuccess) return e; } while (0)
        auto stream = context->stream;
        int count = context->count, width = context->width, height = context->height;
        CHECK(cudaMemcpyAsync(context->d_rgb, rgb, size_t(count) * 3, cudaMemcpyHostToDevice, stream));
        CHECK(cudaMemcpyAsync(context->d_depth, depth, size_t(count) * sizeof(float), cudaMemcpyHostToDevice, stream));
        CHECK(cudaMemcpyAsync(context->d_shift, shift, size_t(count) * sizeof(float), cudaMemcpyHostToDevice, stream));
        CHECK(cudaMemsetAsync(context->d_owners, 0, size_t(count) * sizeof(unsigned long long), stream));
        splat<<<(count + 255) / 256, 256, 0, stream>>>(context->d_depth, context->d_shift,
            context->d_owners, width, count, coverage != 0);
        CHECK(cudaGetLastError());
        resolve<<<(height + 63) / 64, 64, 0, stream>>>(context->d_rgb, context->d_owners,
            context->d_output, width, height);
        CHECK(cudaGetLastError());
        CHECK(cudaMemcpyAsync(output, context->d_output, size_t(count) * 3, cudaMemcpyDeviceToHost, stream));
        CHECK(cudaStreamSynchronize(stream));
        return cudaSuccess;
#undef CHECK
    };
    auto result = run();
    // Host arrays may be released immediately by the caller on an exception.
    if (result != cudaSuccess) cudaStreamSynchronize(context->stream);
    return int(result);
}

__global__ void negate_shift(float* shift, int count) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < count) shift[i] = -shift[i];
}

// Live paired-eye handoff: RGB/depth/left shift uploaded once, shared on the
// owned stream for both eyes. Host buffers remain alive through final sync.
extern "C" __declspec(dllexport) int projection_run_pair(
    void* handle, const unsigned char* rgb, const float* depth, const float* left_shift,
    unsigned char* left, unsigned char* right, int coverage) {
    auto context = static_cast<ProjectionContext*>(handle);
    if (!context || !rgb || !depth || !left_shift || !left || !right)
        return int(cudaErrorInvalidValue);
    int device = -1;
    auto result = cudaGetDevice(&device);
    if (result != cudaSuccess) return int(result);
    if (device != context->device) return int(cudaErrorInvalidDevice);
    auto run = [&]() -> cudaError_t {
#define CHECK(call) do { cudaError_t e = (call); if (e != cudaSuccess) return e; } while (0)
        int count = context->count, width = context->width, height = context->height;
        auto stream = context->stream;
        CHECK(cudaMemcpyAsync(context->d_rgb, rgb, size_t(count) * 3, cudaMemcpyHostToDevice, stream));
        CHECK(cudaMemcpyAsync(context->d_depth, depth, size_t(count) * 4, cudaMemcpyHostToDevice, stream));
        CHECK(cudaMemcpyAsync(context->d_shift, left_shift, size_t(count) * 4, cudaMemcpyHostToDevice, stream));
        for (int eye = 0; eye < 2; ++eye) {
            if (eye) {
                negate_shift<<<(count + 255) / 256, 256, 0, stream>>>(context->d_shift, count);
                CHECK(cudaGetLastError());
            }
            CHECK(cudaMemsetAsync(context->d_owners, 0, size_t(count) * 8, stream));
            splat<<<(count + 255) / 256, 256, 0, stream>>>(context->d_depth, context->d_shift,
                context->d_owners, width, count, coverage != 0);
            CHECK(cudaGetLastError());
            resolve<<<(height + 63) / 64, 64, 0, stream>>>(context->d_rgb, context->d_owners,
                context->d_output, width, height);
            CHECK(cudaGetLastError());
            CHECK(cudaMemcpyAsync(eye ? right : left, context->d_output, size_t(count) * 3,
                cudaMemcpyDeviceToHost, stream));
        }
        CHECK(cudaStreamSynchronize(stream));
        return cudaSuccess;
#undef CHECK
    };
    result = run();
    if (result != cudaSuccess) cudaStreamSynchronize(context->stream);
    return int(result);
}

extern "C" __declspec(dllexport) int projection_destroy(void* context) {
    return int(release(static_cast<ProjectionContext*>(context)));
}

extern "C" __declspec(dllexport) int project_host(
    const unsigned char* rgb, const float* depth, const float* shift,
    unsigned char* output, int width, int height, int coverage) {
    void* context = nullptr;
    auto result = static_cast<cudaError_t>(projection_create(&context, width, height));
    if (result == cudaSuccess) result = static_cast<cudaError_t>(
        projection_run(context, rgb, depth, shift, output, coverage));
    auto cleanup = static_cast<cudaError_t>(projection_destroy(context));
    return int(result == cudaSuccess ? cleanup : result);
}
