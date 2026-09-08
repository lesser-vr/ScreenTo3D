// Isolated hybrid: exact direct sums for radius 4, rolling windows for 8/12.
// Never loaded by the app.
#define DEPTHSBS_GUIDE_REFERENCE_ONLY 1
#define live_post live_post_reference_export
#define live_post_source live_post_source_reference_export
#include "live_depth.cu"
#undef live_post
#undef live_post_source
#undef DEPTHSBS_GUIDE_REFERENCE_ONLY

constexpr int GUIDE_CHUNK=64;
__global__ void moments_x_hybrid(LiveDepth c,int radius) {
    int segments=(c.w+GUIDE_CHUNK-1)/GUIDE_CHUNK,id=blockIdx.x*blockDim.x+threadIdx.x;
    int y=id/segments,segment=id%segments,x0=segment*GUIDE_CHUNK;if(y>=c.h)return;
    int end=min(c.w,x0+GUIDE_CHUNK),row=y*c.w;double si=0,sp=0,sip=0,sii=0;
    for(int dx=-radius;dx<=radius;dx++) {int j=row+reflect(x0+dx,c.w);float g=c.guide[j],p=c.smooth[j];
        si+=g;sp+=p;sip+=g*p;sii+=g*g;}
    for(int x=x0;x<end;x++) {
        int i=row+x;c.t0[i]=float(si);c.t1[i]=float(sp);c.t2[i]=float(sip);c.t3[i]=float(sii);
        if(x+1<end) {int old=row+reflect(x-radius,c.w),next=row+reflect(x+radius+1,c.w);
            float og=c.guide[old],op=c.smooth[old],ng=c.guide[next],np=c.smooth[next];
            si-=og;sp-=op;sip-=og*op;sii-=og*og;si+=ng;sp+=np;sip+=ng*np;sii+=ng*ng;}
    }
}
__global__ void coefficients_y_hybrid(LiveDepth c,int radius) {
    int chunks=(c.h+GUIDE_CHUNK-1)/GUIDE_CHUNK,id=blockIdx.x*blockDim.x+threadIdx.x;
    int chunk=id/c.w,x=id%c.w,y0=chunk*GUIDE_CHUNK;if(chunk>=chunks)return;
    int end=min(c.h,y0+GUIDE_CHUNK);double si=0,sp=0,sip=0,sii=0;
    for(int dy=-radius;dy<=radius;dy++) {int j=reflect(y0+dy,c.h)*c.w+x;
        si+=c.t0[j];sp+=c.t1[j];sip+=c.t2[j];sii+=c.t3[j];}
    double scale=1.0/((2*radius+1)*(2*radius+1));
    for(int y=y0;y<end;y++) {
        float mi=float(si*scale),mp=float(sp*scale),mip=float(sip*scale),mii=float(sii*scale);
        int i=y*c.w+x;c.a[i]=(mip-mi*mp)/(fmaxf(mii-mi*mi,0.f)+.0001f);c.b[i]=mp-c.a[i]*mi;
        if(y+1<end) {int old=reflect(y-radius,c.h)*c.w+x,next=reflect(y+radius+1,c.h)*c.w+x;
            si-=c.t0[old];sp-=c.t1[old];sip-=c.t2[old];sii-=c.t3[old];
            si+=c.t0[next];sp+=c.t1[next];sip+=c.t2[next];sii+=c.t3[next];}
    }
}
__global__ void coefficients_x_hybrid(LiveDepth c,int radius) {
    int segments=(c.w+GUIDE_CHUNK-1)/GUIDE_CHUNK,id=blockIdx.x*blockDim.x+threadIdx.x;
    int y=id/segments,segment=id%segments,x0=segment*GUIDE_CHUNK;if(y>=c.h)return;
    int end=min(c.w,x0+GUIDE_CHUNK),row=y*c.w;double a=0,b=0;
    for(int dx=-radius;dx<=radius;dx++){int j=row+reflect(x0+dx,c.w);a+=c.a[j];b+=c.b[j];}
    for(int x=x0;x<end;x++) {
        int i=row+x;c.t0[i]=float(a);c.t1[i]=float(b);
        if(x+1<end) {int old=row+reflect(x-radius,c.w),next=row+reflect(x+radius+1,c.w);
            a-=c.a[old];b-=c.b[old];a+=c.a[next];b+=c.b[next];}
    }
}
__global__ void guided_y_hybrid(LiveDepth c,int radius) {
    int chunks=(c.h+GUIDE_CHUNK-1)/GUIDE_CHUNK,id=blockIdx.x*blockDim.x+threadIdx.x;
    int chunk=id/c.w,x=id%c.w,y0=chunk*GUIDE_CHUNK;if(chunk>=chunks)return;
    int end=min(c.h,y0+GUIDE_CHUNK);double a=0,b=0;
    for(int dy=-radius;dy<=radius;dy++){int j=reflect(y0+dy,c.h)*c.w+x;a+=c.t0[j];b+=c.t1[j];}
    double scale=1.0/((2*radius+1)*(2*radius+1));
    for(int y=y0;y<end;y++) {
        int i=y*c.w+x;c.aligned[i]=fminf(1.f,fmaxf(0.f,float(a*scale)*c.guide[i]+float(b*scale)));
        if(y+1<end) {int old=reflect(y-radius,c.h)*c.w+x,next=reflect(y+radius+1,c.h)*c.w+x;
            a-=c.t0[old];b-=c.t1[old];a+=c.t0[next];b+=c.t1[next];}
    }
}
static cudaError_t hybrid_guide(LiveDepth* c,int radius,cudaStream_t stream) {
    if(radius<=4) {
        int blocks=(c->n+255)/256;
        moments_x<<<blocks,256,0,stream>>>(*c,radius);
        coefficients<<<blocks,256,0,stream>>>(*c,radius);
        coefficients_x<<<blocks,256,0,stream>>>(*c,radius);
        guided<<<blocks,256,0,stream>>>(*c,radius);
        return cudaGetLastError();
    }
    int horizontal=c->h*((c->w+GUIDE_CHUNK-1)/GUIDE_CHUNK);
    int vertical=c->w*((c->h+GUIDE_CHUNK-1)/GUIDE_CHUNK);
    moments_x_hybrid<<<(horizontal+255)/256,256,0,stream>>>(*c,radius);
    coefficients_y_hybrid<<<(vertical+255)/256,256,0,stream>>>(*c,radius);
    coefficients_x_hybrid<<<(horizontal+255)/256,256,0,stream>>>(*c,radius);
    guided_y_hybrid<<<(vertical+255)/256,256,0,stream>>>(*c,radius);
    return cudaGetLastError();
}
extern "C" __declspec(dllexport) int live_post(void* handle,const unsigned char* rgb,
    const float* device_depth,int radius,double alpha,float color_threshold,float depth_threshold,int reset,
    float* diagnostic,double transition) {
    auto c=(LiveDepth*)handle;if(!c || !rgb || !device_depth || radius<1 || radius>12)return 1;
    auto s=c->stream;int blocks=(c->n+255)/256;
#define C(call) do {auto e=(call);if(e!=cudaSuccess){cudaStreamSynchronize(s);return int(e);}}while(0)
    C(cudaEventRecord(c->events[2],s));C(cudaMemcpyAsync(c->rgb,rgb,c->n*3,cudaMemcpyHostToDevice,s));
    C(cudaMemsetAsync(c->invalid,0,4,s));check_raw<<<(518*518+255)/256,256,0,s>>>(device_depth,c->invalid);
    resize_depth<<<blocks,256,0,s>>>(device_depth,c->resized,c->w,c->h,c->invalid);C(cudaGetLastError());
    C(cudaEventRecord(c->events[3],s));C(cub::DeviceRadixSort::SortKeys(c->scratch,c->scratch_bytes,c->resized,c->sorted,c->n,0,32,s));
    limits<<<1,1,0,s>>>(c->sorted,c->bounds,c->n,alpha,reset);C(cudaEventRecord(c->events[4],s));
    normalize_motion<<<blocks,256,0,s>>>(*c,color_threshold,reset);
    temporal<<<blocks,256,0,s>>>(*c,float(alpha),float(1.0-alpha),depth_threshold,float(transition),float(double(depth_threshold)-transition),reset);
    C(cudaEventRecord(c->events[5],s));C(hybrid_guide(c,radius,s));C(cudaEventRecord(c->events[6],s));
    C(cudaMemcpyAsync(c->previous,c->rgb,c->n*3,cudaMemcpyDeviceToDevice,s));
    if(diagnostic)C(cudaMemcpyAsync(diagnostic,c->aligned,c->n*4,cudaMemcpyDeviceToHost,s));return 0;
#undef C
}
