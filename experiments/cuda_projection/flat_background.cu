// Full-resolution border-connected background refinement on the live stream.
#include <cuda_runtime.h>
#include <algorithm>
#include <new>
#include <initializer_list>
#include <cmath>

// Borrowed prefix only; Python verifies the live renderer's pinned layout.
struct LivePrefix {
    int w,h,n; cudaStream_t stream;
    float *resized,*sorted,*smooth,*guide,*a,*b,*t0,*t1,*t2,*t3,*aligned,*shift;
    unsigned char *rgb;
};
struct Flat {
    int w,h,n; cudaStream_t stream;
    int *parent=nullptr,*labels=nullptr,*counts=nullptr,*seeds[2]={};
    unsigned char *mask=nullptr,*background=nullptr;
    unsigned int* border=nullptr;
    double *sums=nullptr;
    unsigned int *hist=nullptr,*state=nullptr;
    float *median=nullptr;
    cudaEvent_t events[8]={};
};
constexpr int bins=4096;
__device__ int root(const volatile int* p,int i){while(p[i]!=i)i=p[i];return i;}
__global__ void classify(const unsigned char* rgb,unsigned char* m,int n,int lo,int hi,unsigned int* state){
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;
    bool yes=true;for(int c=0;c<3;c++)yes &= rgb[3*i+c]>=((lo>>(8*c))&255) && rgb[3*i+c]<=((hi>>(8*c))&255);
    m[i]=yes;
    unsigned active=__activemask(),votes=__ballot_sync(active,yes);
    if((threadIdx.x&31)==0)atomicAdd(state,__popc(votes));
}
__global__ void initial(const unsigned char* m,int* p,int w,int n){
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;
    // Horizontal runs: a warp names its nearest run start, or the preceding
    // warp's final pixel. Eight jumps cover even a 4096-pixel uniform row.
    int lane=threadIdx.x&31;
    unsigned starts=__ballot_sync(__activemask(),i%w==0 || m[i]!=m[i-1]);
    unsigned preceding=starts & (0xffffffffu>>(31-lane));
    p[i]=preceding ? i-lane+31-__clz(preceding) : i-lane-1;
}
__global__ void jump(const int* p,int* q,int n){int i=blockIdx.x*blockDim.x+threadIdx.x;if(i<n)q[i]=p[p[i]];}
__device__ void unite(int* p,int a,int b){
    while(true){a=root(p,a);b=root(p,b);if(a==b)return;
        int hi=max(a,b),lo=min(a,b);int old=atomicCAS(p+hi,hi,lo);if(old==hi)return;
    }
}
__global__ void unions(const unsigned char* m,int* p,int w,int n){
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;
    // One edge per intersection of two horizontal runs is sufficient. Linking
    // every pixel of a uniform row would contend on the same pair of roots.
    if(i>=w && m[i]==m[i-w] && (i%w==0 || m[i]!=m[i-1] || m[i-w]!=m[i-w-1]))unite(p,i,i-w);
}
__global__ void run_roots(const int* p,const int* runs,int* map,int n){int i=blockIdx.x*blockDim.x+threadIdx.x;if(i<n && runs[i]==i)map[i]=root(p,i);}
__global__ void remap(int* labels,const int* map,int n){int i=blockIdx.x*blockDim.x+threadIdx.x;if(i<n)labels[i]=map[labels[i]];}
static cudaError_t components(Flat* f,const unsigned char* mask){
    int blocks=(f->n+255)/256;
    initial<<<blocks,256,0,f->stream>>>(mask,f->parent,f->w,f->n);
    for(int k=0;k<8;k++){jump<<<blocks,256,0,f->stream>>>(f->parent,f->labels,f->n);std::swap(f->parent,f->labels);}
    auto status=cudaMemcpyAsync(f->labels,f->parent,f->n*4,cudaMemcpyDeviceToDevice,f->stream);
    if(status!=cudaSuccess)return status;
    unions<<<blocks,256,0,f->stream>>>(mask,f->parent,f->w,f->n);
    run_roots<<<blocks,256,0,f->stream>>>(f->parent,f->labels,f->counts,f->n);
    remap<<<blocks,256,0,f->stream>>>(f->labels,f->counts,f->n);
    return cudaGetLastError();
}
__global__ void mark_border(const unsigned char* m,const int* labels,unsigned int* b,int w,int h){
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=2*(w+h))return;
    int p=i<w?i:(i<2*w?(h-1)*w+i-w:(i<2*w+h?(i-2*w)*w:(i-2*w-h)*w+w-1));
    if(m[p])atomicOr(b+(labels[p]>>5),1u<<(labels[p]&31));
}
__global__ void select_background(unsigned char* mask,unsigned char* bg,const int* labels,const unsigned int* border,int n,unsigned int* state){
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;
    bool yes=mask[i] && ((border[labels[i]>>5]>>(labels[i]&31))&1u);bg[i]=yes;mask[i]=!yes;
    unsigned active=__activemask(),votes=__ballot_sync(active,yes);
    if((threadIdx.x&31)==0)atomicAdd(state+1,__popc(votes));
}
__global__ void reduce_depth(const float* depth,const unsigned char* bg,const int* labels,double* sums,int* counts,unsigned int* hist,int n){
    __shared__ unsigned int local[bins];
    for(int k=threadIdx.x;k<bins;k+=blockDim.x)local[k]=0;__syncthreads();
    int i=blockIdx.x*blockDim.x+threadIdx.x;
    if(i<n){
        int bin=bg[i]?min(bins-1,max(0,int(depth[i]*(bins-1)+.5f))):-1;
        unsigned active=__activemask();unsigned peers=__match_any_sync(active,bin);
        if(bin>=0 && (threadIdx.x&31)==__ffs(peers)-1)atomicAdd(local+bin,__popc(peers));
        int label=bg[i]?-1:labels[i];
        unsigned group=__match_any_sync(active,label);
        double value=depth[i];
        if(group==0xffffffffu){
            for(int off=16;off;off/=2)value+=__shfl_down_sync(group,value,off);
            if(label>=0 && (threadIdx.x&31)==0){atomicAdd(sums+label,value);atomicAdd(counts+label,32);}
        }else if(label>=0){atomicAdd(sums+label,value);atomicAdd(counts+label,1);}
    }
    __syncthreads();
    for(int k=threadIdx.x;k<bins;k+=blockDim.x)if(local[k])atomicAdd(hist+k,local[k]);
}
__global__ void median_value(const unsigned int* hist,const unsigned int* state,float* result){
    unsigned count=0,a=(state[1]-1)/2,b=state[1]/2;int first=-1;
    for(int k=0;k<bins;k++){count+=hist[k];if(first<0 && count>a)first=k;if(count>b){*result=(first+k)*.5f/(bins-1);return;}}
}
__global__ void seed(const unsigned char* bg,int* a,int* b,int n){int i=blockIdx.x*blockDim.x+threadIdx.x;if(i<n)a[i]=b[i]=bg[i]?i:-1;}
__device__ float distance(int i,int p,int w){if(p<0)return 1.e20f;int dx=abs(i%w-p%w),dy=abs(i/w-p/w);return .955f*max(dx,dy)+.4143f*min(dx,dy);}
__global__ void nearest(const unsigned char* bg,const int* input,int* output,int w,int h,int step){
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=w*h || bg[i])return;
    int x=i%w,y=i/w,best=input[i];float cost=distance(i,best,w);
    for(int dy=-1;dy<=1;dy++)for(int dx=-1;dx<=1;dx++){
        int xx=x+dx*step,yy=y+dy*step;if(xx<0||xx>=w||yy<0||yy>=h)continue;
        int candidate=input[yy*w+xx];float d=distance(i,candidate,w);if(d<cost){cost=d;best=candidate;}
    }output[i]=best;
}
__global__ void apply(float* depth,const unsigned char* bg,const int* labels,const double* sums,const int* counts,const int* seeds,const float* median,int w,int n,float radius){
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;
    if(bg[i]){depth[i]=*median;return;}
    float weight=fminf(distance(i,seeds[i],w)/radius,1.f);
    int label=labels[i];float mean=float(sums[label]/max(1,counts[label]));
    depth[i]=mean*(1-weight)+depth[i]*weight;
}
static cudaError_t release(Flat* f){
    if(!f)return cudaSuccess;auto status=cudaStreamSynchronize(f->stream);
    for(auto event:f->events)if(event){auto e=cudaEventDestroy(event);if(status==cudaSuccess)status=e;}
    for(void* p:std::initializer_list<void*>{f->parent,f->labels,f->counts,f->seeds[0],f->seeds[1],f->mask,f->border,f->background,f->sums,f->hist,f->state,f->median})
        if(p){auto e=cudaFree(p);if(status==cudaSuccess)status=e;}
    delete f;return status;
}
extern "C" __declspec(dllexport) int flat_create(void** out,int w,int h,void* stream){
    if(!out||!stream||w<16||h<16||w>4096||h>2160)return 1;*out=nullptr;
    auto f=new(std::nothrow) Flat{w,h,w*h,(cudaStream_t)stream};if(!f)return 2;
#define ALLOC(field,bytes) do{auto e=cudaMalloc(&f->field,bytes);if(e!=cudaSuccess){release(f);return int(e)+10;}}while(0)
    ALLOC(parent,f->n*4);ALLOC(labels,f->n*4);ALLOC(counts,f->n*4);ALLOC(sums,size_t(f->n)*8);
    ALLOC(seeds[0],f->n*4);ALLOC(seeds[1],f->n*4);ALLOC(mask,f->n);ALLOC(border,((f->n+31)/32)*4);ALLOC(background,f->n);
    ALLOC(hist,bins*4);ALLOC(state,8);ALLOC(median,4);
    for(auto& event:f->events){auto e=cudaEventCreate(&event);if(e!=cudaSuccess){release(f);return int(e)+10;}}
#undef ALLOC
    *out=f;return 0;
}
extern "C" __declspec(dllexport) int flat_destroy(void* p){return int(release(static_cast<Flat*>(p)));}
extern "C" __declspec(dllexport) int flat_apply(void* p,void* live,int lo,int hi,float coverage,int radius,int* applied){
    if(!p||!live||!applied||!std::isfinite(coverage)||coverage<=0||coverage>.98f||radius<1||radius>64)return 1;
    auto f=static_cast<Flat*>(p);auto c=static_cast<LivePrefix*>(live);
    if(c->w!=f->w||c->h!=f->h||c->stream!=f->stream)return 1;
    *applied=0;int blocks=(f->n+255)/256;unsigned int state[2];
#define CHECK(call) do{auto e=(call);if(e!=cudaSuccess)return int(e)+10;}while(0)
    CHECK(cudaMemsetAsync(f->state,0,8,f->stream));
    CHECK(cudaEventRecord(f->events[0],f->stream));
    classify<<<blocks,256,0,f->stream>>>(c->rgb,f->mask,f->n,lo,hi,f->state);
    CHECK(cudaMemcpyAsync(state,f->state,4,cudaMemcpyDeviceToHost,f->stream));CHECK(cudaStreamSynchronize(f->stream));
    double matching=double(state[0])/f->n;if(matching<coverage||matching>.98)return 0;
    CHECK(cudaEventRecord(f->events[1],f->stream));
    CHECK(components(f,f->mask));CHECK(cudaMemsetAsync(f->border,0,((f->n+31)/32)*4,f->stream));
    CHECK(cudaEventRecord(f->events[2],f->stream));
    mark_border<<<(2*(f->w+f->h)+255)/256,256,0,f->stream>>>(f->mask,f->labels,f->border,f->w,f->h);
    select_background<<<blocks,256,0,f->stream>>>(f->mask,f->background,f->labels,f->border,f->n,f->state);
    CHECK(cudaMemcpyAsync(state,f->state,8,cudaMemcpyDeviceToHost,f->stream));CHECK(cudaStreamSynchronize(f->stream));
    if(double(state[1])/f->n<coverage){*applied=-1;return 0;}
    CHECK(cudaEventRecord(f->events[3],f->stream));
    CHECK(components(f,f->mask));
    CHECK(cudaEventRecord(f->events[4],f->stream));
    CHECK(cudaMemsetAsync(f->sums,0,size_t(f->n)*8,f->stream));CHECK(cudaMemsetAsync(f->counts,0,f->n*4,f->stream));
    CHECK(cudaMemsetAsync(f->hist,0,bins*4,f->stream));
    reduce_depth<<<blocks,256,0,f->stream>>>(c->aligned,f->background,f->labels,f->sums,f->counts,f->hist,f->n);
    median_value<<<1,1,0,f->stream>>>(f->hist,f->state,f->median);
    CHECK(cudaEventRecord(f->events[5],f->stream));
    seed<<<blocks,256,0,f->stream>>>(f->background,f->seeds[0],f->seeds[1],f->n);
    int source=0,step=1;while(step<radius*4)step*=2;
    for(;step;step/=2){nearest<<<blocks,256,0,f->stream>>>(f->background,f->seeds[source],f->seeds[1-source],f->w,f->h,step);source=1-source;}
    // Local propagation resolves narrow concave Voronoi wedges that the coarse
    // jumps can miss. The contract still measures against the CPU chamfer field.
    for(int repeat=0;repeat<8;repeat++){
        nearest<<<blocks,256,0,f->stream>>>(f->background,f->seeds[source],f->seeds[1-source],f->w,f->h,1);source=1-source;
    }
    CHECK(cudaEventRecord(f->events[6],f->stream));
    apply<<<blocks,256,0,f->stream>>>(c->aligned,f->background,f->labels,f->sums,f->counts,f->seeds[source],f->median,f->w,f->n,float(radius*4));
    CHECK(cudaEventRecord(f->events[7],f->stream));
    CHECK(cudaGetLastError());CHECK(cudaStreamSynchronize(f->stream));*applied=1;return 0;
#undef CHECK
}
extern "C" __declspec(dllexport) int flat_times(void* p,float* out){
    if(!p||!out)return 1;auto f=static_cast<Flat*>(p);
    for(int k=0;k<7;k++){auto e=cudaEventElapsedTime(out+k,f->events[k],f->events[k+1]);if(e!=cudaSuccess)return int(e)+10;}return 0;
}
// Explicit test boundary: same kernels, no renderer/model dependencies.
extern "C" __declspec(dllexport) int flat_test(void* p,const unsigned char* rgb,const float* input,float* output,unsigned char* mask,int lo,int hi,float coverage,int radius,int* applied){
    if(!p||!rgb||!input||!output||!mask)return 1;auto f=static_cast<Flat*>(p);
    unsigned char* device_rgb=nullptr;float* depth=nullptr;
    auto status=cudaMalloc(&device_rgb,f->n*3);if(status!=cudaSuccess)return int(status)+10;
    status=cudaMalloc(&depth,f->n*4);if(status!=cudaSuccess){cudaFree(device_rgb);return int(status)+10;}
    status=cudaMemcpyAsync(device_rgb,rgb,f->n*3,cudaMemcpyHostToDevice,f->stream);
    if(status==cudaSuccess)status=cudaMemcpyAsync(depth,input,f->n*4,cudaMemcpyHostToDevice,f->stream);
    LivePrefix c{};c.w=f->w;c.h=f->h;c.n=f->n;c.stream=f->stream;c.rgb=device_rgb;c.aligned=depth;
    int result=status==cudaSuccess?flat_apply(p,&c,lo,hi,coverage,radius,applied):int(status)+10;
    if(!result){status=cudaMemcpyAsync(output,depth,f->n*4,cudaMemcpyDeviceToHost,f->stream);
        if(status==cudaSuccess && *applied==1)status=cudaMemcpyAsync(mask,f->background,f->n,cudaMemcpyDeviceToHost,f->stream);
        if(status==cudaSuccess)status=cudaStreamSynchronize(f->stream);if(status!=cudaSuccess)result=int(status)+10;}
    cudaFree(depth);cudaFree(device_rgb);return result;
}
