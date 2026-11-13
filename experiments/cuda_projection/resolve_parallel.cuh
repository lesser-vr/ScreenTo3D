#pragma once
#include <cub/block/block_scan.cuh>

struct ResolveMax {
    __device__ int operator()(int a, int b) const { return a > b ? a : b; }
};

// Same owner selection as resolve(): nearest valid positions on either side,
// smaller quantized depth wins; equal depth chooses the left position.
// One block per row; no per-frame allocation or cross-row dependency.
template<int Items>
__global__ void resolve_parallel(const unsigned char* rgb,
    const unsigned long long* owners, unsigned char* output, int width) {
    using Scan = cub::BlockScan<int, 256>;
    __shared__ typename Scan::TempStorage scan;
    __shared__ int nearest_left[256 * Items];
    int values[Items];
    const int row = blockIdx.x * width;
    const int first = threadIdx.x * Items;
    #pragma unroll
    for (int i = 0; i < Items; ++i) {
        const int x = first + i;
        values[i] = x < width && owners[row + x] ? x : -1;
    }
    Scan(scan).InclusiveScan(values, values, ResolveMax());
    #pragma unroll
    for (int i = 0; i < Items; ++i) nearest_left[first + i] = values[i];
    __syncthreads();
    // Scan reversed coordinates to obtain the closest valid right position.
    #pragma unroll
    for (int i = 0; i < Items; ++i) {
        const int reverse = first + i;
        const int x = width - 1 - reverse;
        values[i] = x >= 0 && owners[row + x] ? reverse : -1;
    }
    Scan(scan).InclusiveScan(values, values, ResolveMax());
    #pragma unroll
    for (int i = 0; i < Items; ++i) {
        const int x = width - 1 - (first + i);
        if (x < 0) continue;
        int chosen = x;
        if (!owners[row + x]) {
            const int left = nearest_left[x];
            const int right = values[i] < 0 ? width : width - 1 - values[i];
            chosen = left;
            if (left < 0 || (right < width &&
                (owners[row + right] >> 32) < (owners[row + left] >> 32)))
                chosen = right;
        }
        const int source = chosen < width
            ? int(owners[row + chosen] & 0xffffffffULL) : row + x;
        copy_pixel(rgb, output, row + x, source);
    }
}

// Occupancy words allow coalesced owner loads and exact nearest-neighbor lookup.
// Prefix/suffix searches happen once per 32 pixels, rather than a scan of pixels.
template<int Items>
__global__ void resolve_bitmap(const unsigned char* rgb,const unsigned long long* owners,
    unsigned char* output,int width) {
    __shared__ unsigned int masks[128];
    __shared__ int left_word[128],right_word[128];
    unsigned long long own[Items];
    int tid=threadIdx.x,row=blockIdx.x*width,words=(width+31)/32;
    #pragma unroll
    for(int k=0;k<Items;k++) {
        int x=tid+k*256;
        own[k]=x<width?owners[row+x]:0;
        unsigned int bits=__ballot_sync(0xffffffffu,own[k]!=0);
        if((tid&31)==0 && (x>>5)<words)masks[x>>5]=bits;
    }
    __syncthreads();
    if(tid<words) {
        int l=tid-1,r=tid+1;
        while(l>=0 && !masks[l])--l;
        while(r<words && !masks[r])++r;
        left_word[tid]=l;right_word[tid]=r;
    }
    __syncthreads();
    #pragma unroll
    for(int k=0;k<Items;k++) {
        int x=tid+k*256;if(x>=width)continue;
        unsigned long long selected=own[k];
        if(!selected) {
            int word=x>>5,lane=x&31;
            unsigned int lbits=masks[word]&(0xffffffffu>>(31-lane));
            unsigned int rbits=masks[word]&(0xffffffffu<<lane);
            int lw=left_word[word],rw=right_word[word];
            int left=lbits?(word*32+31-__clz(lbits)):(lw<0?-1:lw*32+31-__clz(masks[lw]));
            int right=rbits?(word*32+__ffs(rbits)-1):(rw>=words?width:rw*32+__ffs(masks[rw])-1);
            unsigned long long a=left<0?0:owners[row+left],b=right>=width?0:owners[row+right];
            selected=left<0?b:(right<width && (b>>32)<(a>>32)?b:a);
        }
        copy_pixel(rgb,output,row+x,selected?int(selected&0xffffffffULL):row+x);
    }
}

static void launch_resolve_parallel(const unsigned char* rgb,
    const unsigned long long* owners, unsigned char* output,
    int width, int height, cudaStream_t stream) {
#ifdef SCREENTO3D_BITMAP_RESOLVE
    if(width<=1024)resolve_bitmap<4><<<height,256,0,stream>>>(rgb,owners,output,width);
    else if(width<=2048)resolve_bitmap<8><<<height,256,0,stream>>>(rgb,owners,output,width);
    else resolve_bitmap<16><<<height,256,0,stream>>>(rgb,owners,output,width);
#else
    if (width <= 1024)
        resolve_parallel<4><<<height, 256, 0, stream>>>(rgb, owners, output, width);
    else if (width <= 2048)
        resolve_parallel<8><<<height, 256, 0, stream>>>(rgb, owners, output, width);
    else
        resolve_parallel<16><<<height, 256, 0, stream>>>(rgb, owners, output, width);
#endif
}
