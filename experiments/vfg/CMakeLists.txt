cmake_minimum_required(VERSION 3.24)
project(ScreenTo3DVfgProbe LANGUAGES CXX)
find_package(CUDAToolkit REQUIRED)
if(NOT EXISTS "${VFXSDK_ROOT}/nvvfx/include/nvVideoEffects.h")
  message(FATAL_ERROR "Set VFXSDK_ROOT to the official extracted SDK")
endif()
add_executable(vfg_probe probe.cpp
  "${VFXSDK_ROOT}/nvvfx/src/nvVideoEffectsProxy.cpp"
  "${VFXSDK_ROOT}/nvvfx/src/nvCVImageProxy.cpp")
target_compile_features(vfg_probe PRIVATE cxx_std_17)
target_compile_definitions(vfg_probe PRIVATE NOMINMAX WIN32_LEAN_AND_MEAN)
target_include_directories(vfg_probe PRIVATE "${VFXSDK_ROOT}/nvvfx/include"
  "${VFXSDK_ROOT}/features/nvvfxvideoframegeneration/include")
target_link_libraries(vfg_probe PRIVATE CUDA::cudart_static)
