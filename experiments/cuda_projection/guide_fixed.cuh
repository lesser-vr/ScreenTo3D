// Fixed radius, 2-D launch. Default retains the reference double sums.
// Experimental FP32 accumulation is built separately and requires bounded-error
// depth, stereo and temporal validation before its artifact can be pinned.
#if defined(SCREENTO3D_GUIDE_COMPENSATED)
struct GuideAccum {
    // TwoSum retains each addition's residual in a second FP32 component.
    // Unlike a rounded Kahan result, it carries low bits into the final mean.
    // Inputs here are bounded normalized moments/regularized coefficients; this
    // is not a general arbitrary-exponent replacement for double arithmetic.
    float hi=0,lo=0;
    __device__ GuideAccum(int=0) {}
    __device__ void operator+=(float value) {
        float next=__fadd_rn(hi,value),back=__fsub_rn(next,hi);
        float error=__fadd_rn(__fsub_rn(hi,__fsub_rn(next,back)),__fsub_rn(value,back));
        lo=__fadd_rn(lo,error);hi=next;
    }
    __device__ operator double() const {return double(hi)+double(lo);}
};
#elif defined(SCREENTO3D_GUIDE_FLOAT)
using GuideAccum=float;
#else
using GuideAccum=double;
#endif
template<int R> __global__ void moments_fixed(LiveDepth c) {
    int x=blockIdx.x*32+threadIdx.x,y=blockIdx.y*8+threadIdx.y;
    if(x>=c.w || y>=c.h)return;
    int row=y*c.w;GuideAccum si=0,sp=0,sip=0,sii=0;
    #pragma unroll
    for(int dx=-R;dx<=R;dx++) {int j=row+reflect(x+dx,c.w);float g=c.guide[j],p=c.smooth[j];
        si+=g;sp+=p;sip+=g*p;sii+=g*g;}
    int i=row+x;c.t0[i]=float(si);c.t1[i]=float(sp);c.t2[i]=float(sip);c.t3[i]=float(sii);
}
template<int R> __global__ void coefficients_fixed(LiveDepth c) {
    int x=blockIdx.x*32+threadIdx.x,y=blockIdx.y*8+threadIdx.y;
    if(x>=c.w || y>=c.h)return;
    GuideAccum si=0,sp=0,sip=0,sii=0;
    #pragma unroll
    for(int dy=-R;dy<=R;dy++){int j=reflect(y+dy,c.h)*c.w+x;
        si+=c.t0[j];sp+=c.t1[j];sip+=c.t2[j];sii+=c.t3[j];}
    double scale=1.0/((2*R+1)*(2*R+1));
    float mi=float(si*scale),mp=float(sp*scale),mip=float(sip*scale),mii=float(sii*scale);
    int i=y*c.w+x;c.a[i]=(mip-mi*mp)/(fmaxf(mii-mi*mi,0.f)+.0001f);c.b[i]=mp-c.a[i]*mi;
}
template<int R> __global__ void coefficients_x_fixed(LiveDepth c) {
    int x=blockIdx.x*32+threadIdx.x,y=blockIdx.y*8+threadIdx.y;
    if(x>=c.w || y>=c.h)return;
    int row=y*c.w;GuideAccum a=0,b=0;
    #pragma unroll
    for(int dx=-R;dx<=R;dx++){int j=row+reflect(x+dx,c.w);a+=c.a[j];b+=c.b[j];}
    int i=row+x;c.t0[i]=float(a);c.t1[i]=float(b);
}
template<int R> __global__ void guided_fixed(LiveDepth c) {
    int x=blockIdx.x*32+threadIdx.x,y=blockIdx.y*8+threadIdx.y;
    if(x>=c.w || y>=c.h)return;
    GuideAccum a=0,b=0;
    #pragma unroll
    for(int dy=-R;dy<=R;dy++){int j=reflect(y+dy,c.h)*c.w+x;a+=c.t0[j];b+=c.t1[j];}
    double scale=1.0/((2*R+1)*(2*R+1));int i=y*c.w+x;
    c.aligned[i]=fminf(1.f,fmaxf(0.f,float(a*scale)*c.guide[i]+float(b*scale)));
}
template<int R> static cudaError_t fixed_guide(LiveDepth* c,cudaStream_t stream) {
    dim3 grid((c->w+31)/32,(c->h+7)/8),block(32,8);
    moments_fixed<R><<<grid,block,0,stream>>>(*c);
    coefficients_fixed<R><<<grid,block,0,stream>>>(*c);
    coefficients_x_fixed<R><<<grid,block,0,stream>>>(*c);
    guided_fixed<R><<<grid,block,0,stream>>>(*c);
    return cudaGetLastError();
}
