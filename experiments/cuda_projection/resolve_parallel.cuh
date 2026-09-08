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

static void launch_resolve_parallel(const unsigned char* rgb,
    const unsigned long long* owners, unsigned char* output,
    int width, int height, cudaStream_t stream) {
    if (width <= 1024)
        resolve_parallel<4><<<height, 256, 0, stream>>>(rgb, owners, output, width);
    else if (width <= 2048)
        resolve_parallel<8><<<height, 256, 0, stream>>>(rgb, owners, output, width);
    else
        resolve_parallel<16><<<height, 256, 0, stream>>>(rgb, owners, output, width);
}
