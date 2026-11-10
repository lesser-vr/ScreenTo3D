// Experimental 3:2 area reduction. Extend the last row/column for odd sizes.
__global__ void guide_reduce(LiveDepth full, LiveDepth low) {
    int x=blockIdx.x*blockDim.x+threadIdx.x, y=blockIdx.y*blockDim.y+threadIdx.y;
    if(x>=low.w || y>=low.h)return;
    int sx=3*x/2, sy=3*y/2;
    int x1=min(sx+1,full.w-1), y1=min(sy+1,full.h-1);
    float wx=(1+(x&1))/3.f, wy=(1+(y&1))/3.f;
    int indices[]={sy*full.w+sx,sy*full.w+x1,y1*full.w+sx,y1*full.w+x1};
    float weights[]={(1-wx)*(1-wy),wx*(1-wy),(1-wx)*wy,wx*wy};
    float guide=0, depth=0;
    #pragma unroll
    for(int k=0;k<4;k++) {
        guide+=weights[k]*full.guide[indices[k]];
        depth+=weights[k]*full.smooth[indices[k]];
    }
    low.guide[y*low.w+x]=guide;
    low.smooth[y*low.w+x]=depth;
}

template<int R> __global__ void mean_guide_coefficients(LiveDepth low) {
    int x=blockIdx.x*blockDim.x+threadIdx.x, y=blockIdx.y*blockDim.y+threadIdx.y;
    if(x>=low.w || y>=low.h)return;
    GuideAccum a=0,b=0;
    #pragma unroll
    for(int dy=-R;dy<=R;dy++) {
        int j=reflect(y+dy,low.h)*low.w+x;
        a+=low.t0[j]; b+=low.t1[j];
    }
    constexpr double scale=1.0/((2*R+1)*(2*R+1));
    low.a[y*low.w+x]=float(a*scale);
    low.b[y*low.w+x]=float(b*scale);
}

__global__ void guide_reconstruct(LiveDepth full, LiveDepth low) {
    int x=blockIdx.x*blockDim.x+threadIdx.x, y=blockIdx.y*blockDim.y+threadIdx.y;
    if(x>=full.w || y>=full.h)return;
    float u=fminf(low.w-1,fmaxf(0,(x+.5f)*(2.f/3)-.5f));
    float v=fminf(low.h-1,fmaxf(0,(y+.5f)*(2.f/3)-.5f));
    int ix=int(u), iy=int(v), ix1=min(ix+1,low.w-1), iy1=min(iy+1,low.h-1);
    float wx=u-ix, wy=v-iy;
    int indices[]={iy*low.w+ix,iy*low.w+ix1,iy1*low.w+ix,iy1*low.w+ix1};
    float weights[]={(1-wx)*(1-wy),wx*(1-wy),(1-wx)*wy,wx*wy};
    float a=0,b=0;
    #pragma unroll
    for(int k=0;k<4;k++) {
        a+=weights[k]*low.a[indices[k]]; b+=weights[k]*low.b[indices[k]];
    }
    int i=y*full.w+x;
    full.aligned[i]=fminf(1.f,fmaxf(0.f,a*full.guide[i]+b));
}

static cudaError_t guide_two_thirds(LiveDepth* full,cudaStream_t stream) {
    LiveDepth low=*full;
    low.w=(2*full->w+2)/3; low.h=(2*full->h+2)/3; low.n=low.w*low.h;
    // Borrow disjoint tails of the existing coefficient buffers. Tiny shapes
    // without enough spare capacity retain the full-resolution filter.
    if(2*low.n>full->n)return fixed_guide<8>(full,stream);
    low.guide=full->a+low.n; low.smooth=full->b+low.n;
    dim3 block(32,8), grid((low.w+31)/32,(low.h+7)/8);
    guide_reduce<<<grid,block,0,stream>>>(*full,low);
    moments_fixed<5><<<grid,block,0,stream>>>(low);
    coefficients_fixed<5><<<grid,block,0,stream>>>(low);
    coefficients_x_fixed<5><<<grid,block,0,stream>>>(low);
    mean_guide_coefficients<5><<<grid,block,0,stream>>>(low);
    dim3 full_grid((full->w+31)/32,(full->h+7)/8);
    guide_reconstruct<<<full_grid,block,0,stream>>>(*full,low);
    return cudaGetLastError();
}
