/*M///////////////////////////////////////////////////////////////////////////////////////
//
//  IMPORTANT: READ BEFORE DOWNLOADING, COPYING, INSTALLING OR USING.
//
//  By downloading, copying, installing or using the software you agree to this license.
//  If you do not agree to this license, do not download, install,
//  copy or use the software.
//
//
//                           License Agreement
//                For Open Source Computer Vision Library
//
// Copyright (C) 2000-2008, 2017, Intel Corporation, all rights reserved.
// Copyright (C) 2009, Willow Garage Inc., all rights reserved.
// Copyright (C) 2014-2015, Itseez Inc., all rights reserved.
// Third party copyrights are property of their respective owners.
//
// Redistribution and use in source and binary forms, with or without modification,
// are permitted provided that the following conditions are met:
//
//   * Redistribution's of source code must retain the above copyright notice,
//     this list of conditions and the following disclaimer.
//
//   * Redistribution's in binary form must reproduce the above copyright notice,
//     this list of conditions and the following disclaimer in the documentation
//     and/or other materials provided with the distribution.
//
//   * The name of the copyright holders may not be used to endorse or promote products
//     derived from this software without specific prior written permission.
//
// This software is provided by the copyright holders and contributors "as is" and
// any express or implied warranties, including, but not limited to, the implied
// warranties of merchantability and fitness for a particular purpose are disclaimed.
// In no event shall the Intel Corporation or contributors be liable for any direct,
// indirect, incidental, special, exemplary, or consequential damages
// (including, but not limited to, procurement of substitute goods or services;
// loss of use, data, or profits; or business interruption) however caused
// and on any theory of liability, whether in contract, strict liability,
// or tort (including negligence or otherwise) arising in any way out of
// the use of this software, even if advised of the possibility of such damage.
//
//M*/
// Cubic coefficients and uint8 linear arithmetic adapted from OpenCV
// modules/imgproc/src/resize.cpp (4.x). Retain the above notice with binaries.
// Source-sized RGB/BGRA -> normalized CHW. VDA resizes float32 pixels;
// DA2 Base resizes float64 pixels. Both normalize the resized value in double.
#include <cuda_runtime.h>
#include <cstdint>

#ifdef DEPTHSBS_VDA_INPUT
using ResizePixel = float;
#define PREPARE_ENTRY vda_prepare
#else
using ResizePixel = double;
#define PREPARE_ENTRY base_prepare
#endif

__device__ void weights(float x, float* c) {
    const float a = -.75f;
    c[0] = ((a*(x+1)-5*a)*(x+1)+8*a)*(x+1)-4*a;
    c[1] = ((a+2)*x-(a+3))*x*x+1;
    c[2] = ((a+2)*(1-x)-(a+3))*(1-x)*(1-x)+1;
    c[3] = 1.f-c[0]-c[1]-c[2];
}

__global__ void prepare(const unsigned char* src, size_t pitch, int w, int h,
    int channels, int oh, int ow, int top, int left, int rh, int rw, float* out) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;
    if(i>=oh*ow*3)return;
    int c=i/(oh*ow), y=(i/ow)%oh, x=i%ow;
    x=min(max(x-left,0),rw-1); y=min(max(y-top,0),rh-1);
    double px=(x+.5)*(double(w)/rw)-.5, py=(y+.5)*(double(h)/rh)-.5;
#ifdef DEPTHSBS_VDA_INPUT
    int sx=int(floor(px)), sy=int(floor(py));
    float fx=float(px-sx), fy=float(py-sy);
#else
    float fx=float(px), fy=float(py);
    int sx=int(floorf(fx)), sy=int(floorf(fy)); fx-=sx; fy-=sy;
#endif
    float wx[4],wy[4]; weights(fx,wx); weights(fy,wy);
    ResizePixel rows[4];
    for(int j=0;j<4;++j) {
        const unsigned char* row=src+size_t(min(max(sy+j-1,0),h-1))*pitch;
        ResizePixel v[4];
        for(int k=0;k<4;++k)
            v[k]=(ResizePixel(row[min(max(sx+k-1,0),w-1)*channels+(channels==4?2-c:c)])/ResizePixel(255))*wx[k];
        rows[j]=((v[0]+v[1])+v[2])+v[3];
    }
    double value=((rows[0]*wy[0]+rows[1]*wy[1])+rows[2]*wy[2])+rows[3]*wy[3];
    const double mean[3]={.485,.456,.406},sd[3]={.229,.224,.225};
    out[i]=float((value-mean[c])/sd[c]);
}

extern "C" __declspec(dllexport) int PREPARE_ENTRY(const unsigned char* src,
    size_t pitch,int w,int h,int channels,int oh,int ow,int top,int left,int rh,int rw,
    float* out,void* stream) {
    if(!src||!out||!stream||w<16||w>4096||h<16||h>2160||
       (channels!=3&&channels!=4)||pitch<size_t(w*channels)||oh!=518||
       (ow!=896&&ow!=924)||rh<1||rw<1||top<0||left<0||top+rh>oh||left+rw>ow)return 1;
    prepare<<<(oh*ow*3+255)/256,256,0,(cudaStream_t)stream>>>(src,pitch,w,h,channels,oh,ow,top,left,rh,rw,out);
    return int(cudaGetLastError());
}

__global__ void thumbnail(const unsigned char* rgb,int w,int h,unsigned char* dst) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=32*32*3)return;
    int ch=i%3, x=(i/3)%32, y=i/(32*3);
    if(w==32&&h==32){dst[i]=rgb[i];return;}
    float fx=float((x+.5)*(double(w)/32)-.5),fy=float((y+.5)*(double(h)/32)-.5);
    int sx=int(floorf(fx)),sy=int(floorf(fy));fx-=sx;fy-=sy;
    if(sx<0){sx=0;fx=0;}if(sx>=w-1){sx=w-1;fx=0;}
    int x1=min(sx+1,w-1),y0=min(max(sy,0),h-1),y1=min(max(sy+1,0),h-1);
    int a=__float2int_rn((1.f-fx)*2048),b=__float2int_rn(fx*2048);
    int c=__float2int_rn((1.f-fy)*2048),d=__float2int_rn(fy*2048);
    int p=rgb[(y0*w+sx)*3+ch],q=rgb[(y0*w+x1)*3+ch];
    int r=rgb[(y1*w+sx)*3+ch],s=rgb[(y1*w+x1)*3+ch];
    if(w==64&&h==64){dst[i]=(p+q+r+s+2)>>2;return;}
    int row0=p*a+q*b,row1=r*a+s*b;
    dst[i]=((((c*(row0>>4))>>16)+((d*(row1>>4))>>16)+2)>>2);
}
extern "C" __declspec(dllexport) int base_thumbnail(const unsigned char* rgb,int w,int h,unsigned char* dst,void* stream) {
    if(!rgb||!dst||!stream||w<16||w>4096||h<16||h>2160)return 1;
    thumbnail<<<12,256,0,(cudaStream_t)stream>>>(rgb,w,h,dst);
    return int(cudaGetLastError());
}
