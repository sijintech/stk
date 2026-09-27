cmake_minimum_required(VERSION 3.12)


project(nmathfft 
VERSION 1.0.0
DESCRIPTION "The math utilities and useful solvers in fft" 
LANGUAGES C CXX Fortran)


if(CMAKE_PROJECT_NAME STREQUAL PROJECT_NAME)
    set(CMAKE_CXX_EXTENSIONS OFF)
    set_property(GLOBAL PROPERTY USE_FOLDERS ON)
    include(CTest)
endif()

# add_subdirectory(extern)
add_subdirectory(library)

# test when it is the main program
if((CMAKE_PROJECT_NAME STREQUAL PROJECT_NAME OR MODERN_CMAKE_BUILD_TESTING) AND BUILD_TESTING)
    # add_subdirectory(main)
    # add_subdirectory(test)
endif()
