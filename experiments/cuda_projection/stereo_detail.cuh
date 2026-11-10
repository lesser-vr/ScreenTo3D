#pragma once

// Projection-only scratch: t0 is no longer live after guided filtering. It is
// fully overwritten here on the same stream; aligned/history remain immutable.
__host__ __device__ const float* live_projection_depth(const LiveDepth& c) {
    return c.detail_mode&1 ? c.t0 : c.aligned;
}
__device__ float detail_ramp(float lo,float hi,float x) {
    float t=fminf(1.f,fmaxf(0.f,(x-lo)/(hi-lo)));return t*t*(3-2*t);
}
__device__ float rgb_distance(const LiveDepth& c,int a,int b) {
    float d=0;for(int k=0;k<3;k++)d=fmaxf(d,fabsf(float(c.rgb[a*3+k])-c.rgb[b*3+k]));
    return d;
}
__global__ void contour_depth(LiveDepth c) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=c.n)return;
    int x=i%c.w;float z=c.aligned[i];c.t0[i]=z;
    if(x<2||x>=c.w-2)return;
    float l=c.aligned[i-1],r=c.aligned[i+1],gap=fabsf(r-l);
    if(gap<=.06f||z<=fminf(l,r)||z>=fmaxf(l,r))return;
    float plateau=fmaxf(fabsf(c.aligned[i-2]-l),fabsf(c.aligned[i+2]-r));
    float dl=rgb_distance(c,i,i-1),dr=rgb_distance(c,i,i+1);
    float fraction=(z-fminf(l,r))/gap;
    float confidence=detail_ramp(.06f,.12f,gap)*(1-detail_ramp(.01f,.03f,plateau))
        *(1-detail_ramp(4.f,12.f,fminf(dl,dr)))*detail_ramp(24.f,48.f,fmaxf(dl,dr))
        *detail_ramp(0.f,.1f,fraction)*(1-detail_ramp(.9f,1.f,fraction));
    float target=dl<dr?l:r;
    c.t0[i]=z+confidence*fminf(.025f,fmaxf(-.025f,target-z));
}

// Use the farther surface at its inverse-warp coordinate only if both source
// samples belong to that surface. Hidden samples are never read through a near
// object. Otherwise extend a verified local gradient at most four source pixels.
// Text/texture edges, row bounds and depth discontinuities preserve the old fill.
__device__ bool sample_background(const LiveDepth& c,int dst,int source,int away,float* result) {
    const float* depth=c.aligned;
    int row=(source/c.w)*c.w,x=source%c.w;
    float z=depth[source],delta=float(dst%c.w-x)-c.shift[source];
    float position=x+delta;
    int lo=int(floorf(position));float fraction=position-lo;
    if(lo>=0 && lo+1<c.w && fabsf(depth[row+lo]-z)<=.015f && fabsf(depth[row+lo+1]-z)<=.015f) {
        float confidence=1-detail_ramp(.005f,.015f,fmaxf(fabsf(depth[row+lo]-z),fabsf(depth[row+lo+1]-z)));
        for(int k=0;k<3;k++) {
            float sampled=(1-fraction)*c.rgb[(row+lo)*3+k]+fraction*c.rgb[(row+lo+1)*3+k];
            result[k]=c.rgb[source*3+k]+confidence*(sampled-c.rgb[source*3+k]);
        }
        return true;
    }
    if(fabsf(delta)>4.f||x+3*away<0||x+3*away>=c.w)return false;
    float confidence=1-detail_ramp(3.f,4.f,fabsf(delta));
    for(int n=1;n<=3;n++)confidence=fminf(confidence,1-detail_ramp(.005f,.015f,fabsf(depth[source+n*away]-z)));
    float candidate[3];
    for(int k=0;k<3;k++) {
        float v0=c.rgb[source*3+k],v1=c.rgb[(source+away)*3+k];
        float v2=c.rgb[(source+2*away)*3+k],v3=c.rgb[(source+3*away)*3+k];
        float gradient=(v3-v0)/3;
        float residual=fmaxf(fabsf(v1-v0-gradient),fmaxf(fabsf(v2-v1-gradient),fabsf(v3-v2-gradient)));
        confidence=fminf(confidence,(1-detail_ramp(4.f,8.f,fabsf(gradient)))*(1-detail_ramp(1.f,2.f,residual)));
        candidate[k]=fminf(255.f,fmaxf(0.f,v0+gradient*delta*away));
    }
    for(int k=0;k<3;k++)result[k]=c.rgb[source*3+k]+confidence*(candidate[k]-c.rgb[source*3+k]);
    return true;
}
__global__ void fill_background(LiveDepth c) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=c.n||c.owners[i])return;
    int x=i%c.w,left=-1,right=-1;
    for(int d=1;d<=32;d++) {
        if(left<0&&x-d>=0&&c.owners[i-d])left=i-d;
        if(right<0&&x+d<c.w&&c.owners[i+d])right=i+d;
        if(left>=0&&right>=0)break;
    }
    if(left<0||right<0)return;
    int a=int(c.owners[left]&0xffffffffULL),b=int(c.owners[right]&0xffffffffULL);
    const float* depth=c.aligned;
    if(fabsf(depth[a]-depth[b])<=.04f)return;
    int source=depth[a]<depth[b]?a:b,away=source==a?-1:1;
    float rgb[3];
    if(!sample_background(c,i,source,away,rgb))return;
    float confidence=detail_ramp(.04f,.08f,fabsf(depth[a]-depth[b]));
    for(int k=0;k<3;k++) {
        float old=c.output[i*3+k];
        c.output[i*3+k]=(unsigned char)floorf(old+confidence*(rgb[k]-old)+.5f);
    }
}
extern "C" __declspec(dllexport) int live_set_detail(void* handle,int mode) {
    auto c=static_cast<LiveDepth*>(handle);if(!c||mode<0||mode>3)return 1;
    c->detail_mode=mode;return 0;
}
extern "C" __declspec(dllexport) int live_detail_snapshot(void* handle,float* output) {
    auto c=static_cast<LiveDepth*>(handle);if(!c||!output)return 1;
    auto e=cudaMemcpyAsync(output,live_projection_depth(*c),c->n*4,cudaMemcpyDeviceToHost,c->stream);
    if(e!=cudaSuccess)return int(e);return int(cudaStreamSynchronize(c->stream));
}
