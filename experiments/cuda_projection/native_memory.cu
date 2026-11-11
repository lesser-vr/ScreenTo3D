// Bounded memory utilities. Bilinear evaluation retains the PyTorch 2.7.1
// align_corners FP32 operation order; no model or stereo algorithm lives here.
#include <cuda_runtime.h>
#include <cstdint>
#include <cmath>

__global__ void color(const uint8_t* src,uint8_t* dst,int n) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;
    if(i<n){dst[3*i]=src[4*i+2];dst[3*i+1]=src[4*i+1];dst[3*i+2]=src[4*i];}
}
__global__ void finite(const float* src,size_t n,int* invalid) {
    size_t i=size_t(blockIdx.x)*blockDim.x+threadIdx.x;
    if(i<n&&!isfinite(src[i]))atomicOr(invalid,1);
}
__global__ void equal_bytes(const uint8_t* a,const uint8_t* b,size_t n,int* different) {
    size_t i=size_t(blockIdx.x)*blockDim.x+threadIdx.x;
    if(i<n&&a[i]!=b[i])atomicOr(different,1);
}
__global__ void resize_depth(const float* src,int pitch,int ih,int iw,float* dst,int oh,int ow) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=oh*ow)return;
    int y=i/ow,x=i%ow;
    float fy=(oh>1?float(ih-1)/float(oh-1):0.f)*y;
    float fx=(ow>1?float(iw-1)/float(ow-1):0.f)*x;
    int y0=int(fy),x0=int(fx),y1=min(y0+1,ih-1),x1=min(x0+1,iw-1);
    float by=fy-y0,bx=fx-x0,ay=1.f-by,ax=1.f-bx;
    float a=src[y0*pitch+x0],b=src[y0*pitch+x1],c=src[y1*pitch+x0],d=src[y1*pitch+x1];
    float top=__fmaf_rn(ax,a,bx*b),bottom=__fmaf_rn(ax,c,bx*d);
    dst[i]=__fmaf_rn(ay,top,by*bottom);
}
__global__ void pack_cache(const float* const* entries,float* dst,int spatial,int channels) {
    size_t i=size_t(blockIdx.x)*blockDim.x+threadIdx.x;
    if(i>=size_t(spatial)*31*channels)return;
    int c=i%channels,t=(i/channels)%31,s=i/(channels*31);
    dst[i]=entries[t][size_t(s)*channels+c];
}
extern "C" {
__declspec(dllexport) int memory_color(const void* src,void* dst,int w,int h,void* stream) {
    if(!src||!dst||w<16||h<16||w>4096||h>2160)return int(cudaErrorInvalidValue);
    color<<<(w*h+255)/256,256,0,(cudaStream_t)stream>>>((const uint8_t*)src,(uint8_t*)dst,w*h);
    return int(cudaGetLastError());
}
__declspec(dllexport) int memory_finite(const void* src,size_t n,void* flag,void* stream) {
    if(!src||!flag||!n||n>size_t(1024)*1024*256)return int(cudaErrorInvalidValue);
    finite<<<(n+255)/256,256,0,(cudaStream_t)stream>>>((const float*)src,n,(int*)flag);
    return int(cudaGetLastError());
}
__declspec(dllexport) int memory_equal(const void* a,const void* b,size_t n,void* flag,void* stream) {
    if(!a||!b||!flag||!n||n>size_t(4096)*2160*4)return int(cudaErrorInvalidValue);
    equal_bytes<<<(n+255)/256,256,0,(cudaStream_t)stream>>>((const uint8_t*)a,(const uint8_t*)b,n,(int*)flag);
    return int(cudaGetLastError());
}
__declspec(dllexport) int memory_resize(const void* src,int pitch,int ih,int iw,void* dst,int oh,int ow,void* stream) {
    if(!src||!dst||ih<1||iw<1||pitch<iw||ih>2160||pitch>4096||oh<1||ow<1||oh>2160||ow>4096)return int(cudaErrorInvalidValue);
    resize_depth<<<(oh*ow+255)/256,256,0,(cudaStream_t)stream>>>((const float*)src,pitch,ih,iw,(float*)dst,oh,ow);
    return int(cudaGetLastError());
}
__declspec(dllexport) int memory_cache(const void* entries,void* dst,int spatial,int channels,void* stream) {
    if(!entries||!dst||spatial<1||spatial>37*66*4||channels<1||channels>384)return int(cudaErrorInvalidValue);
    size_t n=size_t(spatial)*31*channels;
    pack_cache<<<(n+255)/256,256,0,(cudaStream_t)stream>>>((const float* const*)entries,(float*)dst,spatial,channels);
    return int(cudaGetLastError());
}
}
