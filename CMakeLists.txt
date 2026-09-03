cmake_minimum_required(VERSION 3.28)

project(DepthSBS VERSION 0.1.0 LANGUAGES CXX)

include(CTest)

option(DEPTHSBS_WARNINGS_AS_ERRORS "Treat compiler warnings as errors" ON)

add_library(depthsbs_core
    src/foundation/capabilities.cpp
    src/mode/mode_policy.cpp
    src/platform/windows_nvidia_probe.cpp
)

target_include_directories(depthsbs_core
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_compile_features(depthsbs_core PUBLIC cxx_std_20)

if(MSVC)
    target_compile_options(depthsbs_core PRIVATE /W4 /permissive- /EHsc)
    if(DEPTHSBS_WARNINGS_AS_ERRORS)
        target_compile_options(depthsbs_core PRIVATE /WX)
    endif()
else()
    target_compile_options(depthsbs_core PRIVATE -Wall -Wextra -Wpedantic)
    if(DEPTHSBS_WARNINGS_AS_ERRORS)
        target_compile_options(depthsbs_core PRIVATE -Werror)
    endif()
endif()

if(WIN32)
    target_link_libraries(depthsbs_core PRIVATE version)
endif()

add_executable(depthsbs src/app/main.cpp)
target_link_libraries(depthsbs PRIVATE depthsbs_core)
target_compile_features(depthsbs PRIVATE cxx_std_20)

if(BUILD_TESTING)
    add_executable(depthsbs_tests
        tests/capabilities_tests.cpp
        tests/mode_policy_tests.cpp
        tests/test_main.cpp
    )
    target_link_libraries(depthsbs_tests PRIVATE depthsbs_core)
    target_compile_features(depthsbs_tests PRIVATE cxx_std_20)
    add_test(NAME depthsbs_tests COMMAND depthsbs_tests)
endif()
