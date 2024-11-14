cmake_minimum_required(VERSION 3.12)

Get_Project_Version(NMATHBASIC library/include/nmathbasic/nmathbasic.h)

# Setup project
project(nmathbasic 
VERSION ${PROJECT_VERSION_MAJOR}.${PROJECT_VERSION_MINOR}.${PROJECT_VERSION_PATCH}
DESCRIPTION "The basic math utilities" 
LANGUAGES C CXX Fortran)

# Add test if we are not building from other projects
if(CMAKE_PROJECT_NAME STREQUAL PROJECT_NAME)
    set(CMAKE_CXX_EXTENSIONS OFF)
    set_property(GLOBAL PROPERTY USE_FOLDERS ON)
    include(CTest)
endif()

# Add the sources
# add_subdirectory(extern)
add_subdirectory(library)


# Build test and main
if((CMAKE_PROJECT_NAME STREQUAL PROJECT_NAME OR MODERN_CMAKE_BUILD_TESTING) AND BUILD_TESTING)
    # add_subdirectory(main)
    # add_subdirectory(tests)
endif()






