cmake_minimum_required(VERSION 3.28)

project(DepthSbsTensorRt11Smoke LANGUAGES CXX)

set(DEPTHSBS_TENSORRT_ROOT "" CACHE PATH "TensorRT SDK root")
set(DEPTHSBS_CUDA_ROOT "" CACHE PATH "CUDA Toolkit root")
if(NOT DEPTHSBS_CUDA_ROOT AND DEFINED ENV{CUDA_PATH})
    set(DEPTHSBS_CUDA_ROOT "$ENV{CUDA_PATH}")
endif()
if(NOT DEPTHSBS_TENSORRT_ROOT OR NOT DEPTHSBS_CUDA_ROOT)
    message(FATAL_ERROR "Set DEPTHSBS_TENSORRT_ROOT and DEPTHSBS_CUDA_ROOT")
endif()

find_path(TENSORRT_INCLUDE_DIR NvInfer.h
    PATHS "${DEPTHSBS_TENSORRT_ROOT}/include" NO_DEFAULT_PATH REQUIRED)
find_library(TENSORRT_LIBRARY nvinfer_11
    PATHS "${DEPTHSBS_TENSORRT_ROOT}/lib" NO_DEFAULT_PATH REQUIRED)
find_library(TENSORRT_ONNX_LIBRARY nvonnxparser_11
    PATHS "${DEPTHSBS_TENSORRT_ROOT}/lib" NO_DEFAULT_PATH REQUIRED)
find_path(CUDA_INCLUDE_DIR cuda_runtime_api.h
    PATHS "${DEPTHSBS_CUDA_ROOT}/include" NO_DEFAULT_PATH REQUIRED)

add_executable(depthsbs_tensorrt11_smoke main.cpp)
target_compile_features(depthsbs_tensorrt11_smoke PRIVATE cxx_std_20)
target_include_directories(depthsbs_tensorrt11_smoke PRIVATE
    "${TENSORRT_INCLUDE_DIR}"
    "${CUDA_INCLUDE_DIR}"
)
target_link_libraries(depthsbs_tensorrt11_smoke PRIVATE
    "${TENSORRT_LIBRARY}"
    "${TENSORRT_ONNX_LIBRARY}"
)

if(MSVC)
    target_compile_options(depthsbs_tensorrt11_smoke PRIVATE
        /W4 /WX /permissive- /EHsc /utf-8)
else()
    target_compile_options(depthsbs_tensorrt11_smoke PRIVATE
        -Wall -Wextra -Wpedantic -Werror)
endif()
