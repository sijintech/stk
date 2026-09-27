cmake_minimum_required(VERSION 3.5)

Get_Project_Version(NTEXTUTILS library/include/ntextutils/ntextutils.h)

project(ntextutils 
VERSION ${PROJECT_VERSION_MAJOR}.${PROJECT_VERSION_MINOR}.${PROJECT_VERSION_PATCH}
DESCRIPTION "The string text utilities" 
LANGUAGES C CXX Fortran)

if(CMAKE_PROJECT_NAME STREQUAL PROJECT_NAME)
    set(CMAKE_CXX_EXTENSIONS OFF)
    set_property(GLOBAL PROPERTY USE_FOLDERS ON)
    include(CTest)
endif()



# add_subdirectory(extern)
add_subdirectory(library)


# test when it is the main program
if((CMAKE_PROJECT_NAME STREQUAL PROJECT_NAME OR MODERN_CMAKE_BUILD_TESTING)
    AND BUILD_TESTING)
    add_subdirectory(test)
endif()
