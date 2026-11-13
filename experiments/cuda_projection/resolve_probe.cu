// Standalone diagnostic. Never loaded by the GUI or file converter.
#define SCREENTO3D_GPU_PREVIEW 1
#include "projection.cu"
#include "resolve_parallel.cuh"

extern "C" __declspec(dllexport) int probe_resolve(const unsigned char* rgb,
    const unsigned long long* owners, unsigned char* output, int w, int h,
    int parallel, int repeats, float* milliseconds) {
    if(!rgb || !owners || !output || !milliseconds || w<1 || w>4096 ||
        h<1 || h>2160 || repeats<1 || repeats>1000 || (parallel!=0 && parallel!=1))
        return int(cudaErrorInvalidValue);
    cudaStream_t stream=nullptr;
    cudaEvent_t begin=nullptr,end=nullptr;
    unsigned char *d_rgb=nullptr,*d_output=nullptr;
    unsigned long long* d_owners=nullptr;
    const size_t n=size_t(w)*h;
    auto run=[&]()->cudaError_t {
#define C(call) do {auto e=(call);if(e!=cudaSuccess)return e;}while(0)
        C(cudaStreamCreateWithFlags(&stream,cudaStreamNonBlocking));
        C(cudaEventCreate(&begin));C(cudaEventCreate(&end));
        C(cudaMalloc(&d_rgb,n*3));C(cudaMalloc(&d_output,n*3));
        C(cudaMalloc(&d_owners,n*8));
        C(cudaMemcpyAsync(d_rgb,rgb,n*3,cudaMemcpyHostToDevice,stream));
        C(cudaMemcpyAsync(d_owners,owners,n*8,cudaMemcpyHostToDevice,stream));
        for(int i=-3;i<repeats;i++) {
            C(cudaEventRecord(begin,stream));
            if(parallel)launch_resolve_parallel(d_rgb,d_owners,d_output,w,h,stream);
            else resolve<<<(h+63)/64,64,0,stream>>>(d_rgb,d_owners,d_output,w,h);
            C(cudaGetLastError());C(cudaEventRecord(end,stream));
            C(cudaEventSynchronize(end));
            if(i>=0)C(cudaEventElapsedTime(milliseconds+i,begin,end));
        }
        C(cudaMemcpyAsync(output,d_output,n*3,cudaMemcpyDeviceToHost,stream));
        C(cudaStreamSynchronize(stream));return cudaSuccess;
#undef C
    };
    auto status=run();
    auto keep=[&](cudaError_t e){if(status==cudaSuccess)status=e;};
    if(stream)keep(cudaStreamSynchronize(stream));
    if(begin)keep(cudaEventDestroy(begin));if(end)keep(cudaEventDestroy(end));
    if(d_rgb)keep(cudaFree(d_rgb));if(d_output)keep(cudaFree(d_output));
    if(d_owners)keep(cudaFree(d_owners));if(stream)keep(cudaStreamDestroy(stream));
    return int(status);
}
