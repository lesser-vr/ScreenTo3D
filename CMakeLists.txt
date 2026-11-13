cmake_minimum_required(VERSION 3.28)

project(ScreenTo3D VERSION 1.0.0 LANGUAGES CXX)

include(CTest)

if(DEFINED STEREOTO3D_WARNINGS_AS_ERRORS AND NOT DEFINED SCREENTO3D_WARNINGS_AS_ERRORS)
    set(SCREENTO3D_WARNINGS_AS_ERRORS "${STEREOTO3D_WARNINGS_AS_ERRORS}" CACHE BOOL "Treat compiler warnings as errors")
endif()
if(DEFINED DEPTHSBS_WARNINGS_AS_ERRORS AND NOT DEFINED SCREENTO3D_WARNINGS_AS_ERRORS)
    set(SCREENTO3D_WARNINGS_AS_ERRORS "${DEPTHSBS_WARNINGS_AS_ERRORS}" CACHE BOOL "Treat compiler warnings as errors")
endif()
option(SCREENTO3D_WARNINGS_AS_ERRORS "Treat compiler warnings as errors" ON)

add_library(screento3d_core
    src/foundation/capabilities.cpp
    src/mode/mode_policy.cpp
    src/platform/windows_nvidia_probe.cpp
)

target_include_directories(screento3d_core
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_compile_features(screento3d_core PUBLIC cxx_std_20)

if(MSVC)
    target_compile_options(screento3d_core PRIVATE /W4 /permissive- /EHsc)
    if(SCREENTO3D_WARNINGS_AS_ERRORS)
        target_compile_options(screento3d_core PRIVATE /WX)
    endif()
else()
    target_compile_options(screento3d_core PRIVATE -Wall -Wextra -Wpedantic)
    if(SCREENTO3D_WARNINGS_AS_ERRORS)
        target_compile_options(screento3d_core PRIVATE -Werror)
    endif()
endif()

if(WIN32)
    target_link_libraries(screento3d_core PRIVATE version)
endif()

add_executable(screento3d src/app/main.cpp)
target_link_libraries(screento3d PRIVATE screento3d_core)
target_compile_features(screento3d PRIVATE cxx_std_20)

# Preserve the previous CLI command for existing scripts.
add_custom_command(TARGET screento3d POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        $<TARGET_FILE:screento3d>
        $<TARGET_FILE_DIR:screento3d>/depthsbs${CMAKE_EXECUTABLE_SUFFIX})
add_custom_command(TARGET screento3d POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        $<TARGET_FILE:screento3d>
        $<TARGET_FILE_DIR:screento3d>/stereoto3d${CMAKE_EXECUTABLE_SUFFIX})

if(BUILD_TESTING)
    add_executable(screento3d_tests
        tests/capabilities_tests.cpp
        tests/mode_policy_tests.cpp
        tests/test_main.cpp
    )
    target_link_libraries(screento3d_tests PRIVATE screento3d_core)
    target_compile_features(screento3d_tests PRIVATE cxx_std_20)
    add_test(NAME screento3d_tests COMMAND screento3d_tests)
endif()
