// oVDA input adaptation, NC-SA-UHDV1.0; see LICENSE and README.md.
// FP32 half-pixel bicubic (-0.75), replicate padding and FP32 normalization.
#include <cuda_runtime.h>
#include <cstdint>

__global__ void range_flag(const unsigned char* src, size_t pitch, int w, int h,
                          int channels, int* flag) {
    bool bright=false;
    for(int i=blockIdx.x*blockDim.x+threadIdx.x; i<w*h*3; i+=blockDim.x*gridDim.x) {
        int p=i/3, c=i%3;
        bright |= src[size_t(p/w)*pitch+(p%w)*channels+c]>1;
    }
    if(__syncthreads_or(bright) && threadIdx.x==0) atomicExch(flag,1);
}

__device__ float outer(float x) { return ((-.75f*x+3.75f)*x-6.f)*x+3.f; }
__device__ void cubic(float t,float* a) {
    a[0]=outer(t+1.f);
    a[1]=((1.25f*t-2.25f)*t)*t+1.f;
    float u=1.f-t;
    a[2]=((1.25f*u-2.25f)*u)*u+1.f;
    a[3]=outer(u+1.f);
}

__global__ void prepare(const unsigned char* src,size_t pitch,int w,int h,int channels,
                       int oh,int ow,int top,int left,int rh,int rw,const int* flag,float* dst) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;
    if(i>=3*oh*ow)return;
    int c=i/(oh*ow), y=min(max((i/ow)%oh-top,0),rh-1), x=min(max(i%ow-left,0),rw-1);
    float px=(float(w)/rw)*(x+.5f)-.5f, py=(float(h)/rh)*(y+.5f)-.5f;
    int sx=int(floorf(px)),sy=int(floorf(py));
    float ax[4],ay[4];cubic(px-sx,ax);cubic(py-sy,ay);
    float rows[4];
    for(int j=0;j<4;++j) {
        const unsigned char* row=src+size_t(min(max(sy+j-1,0),h-1))*pitch;
        float v[4];
        for(int k=0;k<4;++k) {
            float value=float(row[min(max(sx+k-1,0),w-1)*channels+(channels==4?2-c:c)]);
            if(*flag)value=value/255.f;
            v[k]=value*ax[k];
        }
        rows[j]=((v[0]+v[1])+v[2])+v[3];
    }
    float value=((rows[0]*ay[0]+rows[1]*ay[1])+rows[2]*ay[2])+rows[3]*ay[3];
    const float mean[3]={.485f,.456f,.406f},sd[3]={.229f,.224f,.225f};
    dst[i]=(value-mean[c])/sd[c];
}

extern "C" __declspec(dllexport) int ovda_prepare(const unsigned char* src,size_t pitch,
    int w,int h,int channels,int oh,int ow,int top,int left,int rh,int rw,
    float* dst,int* flag,void* stream) {
    if(!src||!dst||!flag||!stream||w<16||w>4096||h<16||h>2160||
       (channels!=3&&channels!=4)||pitch<size_t(w*channels)||
       !((oh==518&&(ow==686||ow==896||ow==924))||(oh==392&&ow==700))||
       rh<1||rw<1||top<0||left<0||top+rh>oh||left+rw>ow)return 1;
    auto s=(cudaStream_t)stream;
    auto error=cudaMemsetAsync(flag,0,sizeof(int),s);if(error)return int(error);
    range_flag<<<min(1024,(w*h*3+255)/256),256,0,s>>>(src,pitch,w,h,channels,flag);
    error=cudaGetLastError();if(error)return int(error);
    prepare<<<(3*oh*ow+255)/256,256,0,s>>>(src,pitch,w,h,channels,oh,ow,top,left,rh,rw,flag,dst);
    return int(cudaGetLastError());
}

// Each lane owns all temporal slots of one feature. Reading slot t+1 before
// replacing slot t is safe in place; no other lane reads or writes this feature.
__global__ void shift_cache(float* cache,const float* next,int n,int channels) {
    int lane=blockIdx.x*blockDim.x+threadIdx.x;
    if(lane>=2*n*channels)return;
    int base=(lane/channels)*16*channels+lane%channels;
    for(int t=0;t<14;++t)cache[base+t*channels]=cache[base+(t+1)*channels];
    cache[base+14*channels]=next[lane];
    cache[base+15*channels]=0.f;
}

extern "C" __declspec(dllexport) int ovda_shift_cache(float* cache,const float* next,
    int n,int channels,void* stream) {
    if(!cache||!next||!stream||n<1||n>10000||
       (channels!=64&&channels!=192&&channels!=384))return 1;
    shift_cache<<<(2*n*channels+255)/256,256,0,(cudaStream_t)stream>>>(cache,next,n,channels);
    return int(cudaGetLastError());
}

struct Outputs { const float* pointers[5]; size_t sizes[5]; };
__global__ void finite_outputs(Outputs outputs,size_t total,int* bad) {
    bool invalid=false;
    for(size_t i=blockIdx.x*blockDim.x+threadIdx.x;i<total;i+=blockDim.x*gridDim.x) {
        size_t local=i;int array=0;
        while(array<4&&local>=outputs.sizes[array])local-=outputs.sizes[array++];
        invalid |= !isfinite(outputs.pointers[array][local]);
    }
    if(__syncthreads_or(invalid)&&threadIdx.x==0)atomicExch(bad,1);
}

extern "C" __declspec(dllexport) int ovda_check_outputs(const float* depth,const float* a,
    const float* b,const float* c,const float* d,size_t nd,size_t na,size_t nb,size_t nc,size_t ne,
    int* flag,void* stream) {
    Outputs outputs={{depth,a,b,c,d},{nd,na,nb,nc,ne}};
    if(!flag||!stream)return 1;
    size_t total=0;
    for(int i=0;i<5;++i) {
        if(!outputs.pointers[i]||outputs.sizes[i]<1||outputs.sizes[i]>10000000)return 1;
        total+=outputs.sizes[i];
    }
    auto s=(cudaStream_t)stream;
    auto error=cudaMemsetAsync(flag,0,sizeof(int),s);if(error)return int(error);
    finite_outputs<<<int(min(size_t(1024),(total+255)/256)),256,0,s>>>(outputs,total,flag);
    return int(cudaGetLastError());
}
