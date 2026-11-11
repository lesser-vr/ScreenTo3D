#include <cuda_runtime.h>
#include <cstdint>

__global__ void bgra_to_rgb(const uint8_t* input,size_t pitch,uint8_t* output,int width,int height) {
    const int x=blockIdx.x*blockDim.x+threadIdx.x;
    const int y=blockIdx.y*blockDim.y+threadIdx.y;
    if(x>=width||y>=height)return;
    const auto* source=input+size_t(y)*pitch+x*4;
    auto* target=output+(size_t(y)*width+x)*3;
    target[0]=source[2];target[1]=source[1];target[2]=source[0];
}

extern "C" __declspec(dllexport) int native_bgra_to_rgb(const void* input,size_t pitch,
        void* output,int width,int height,void* stream) {
    if(!input||!output||width<16||height<16||width>4096||height>2160||pitch<size_t(width)*4)
        return int(cudaErrorInvalidValue);
    bgra_to_rgb<<<dim3((width+31)/32,(height+7)/8),dim3(32,8),0,(cudaStream_t)stream>>>(
        (const uint8_t*)input,pitch,(uint8_t*)output,width,height);
    return int(cudaGetLastError());
}
