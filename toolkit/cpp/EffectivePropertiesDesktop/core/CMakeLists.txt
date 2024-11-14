cmake_minimum_required(VERSION 3.12)


set(PJ_NAME muproEffProp)

# if(WIN32)
# set(CMAKE_Fortran_COMPILER "C:/msys64/mingw64/bin/gfortran.exe")
# endif()

project(
    ${PJ_NAME}
    VERSION 0.1.6
    DESCRIPTION "The mupro effective properties module"
    LANGUAGES C CXX Fortran
)

set(CMAKE_BUILD_TYPE Release)

if(CMAKE_PROJECT_NAME STREQUAL PROJECT_NAME)
    set(CMAKE_CXX_EXTENSIONS OFF)
    set_property(GLOBAL PROPERTY USE_FOLDERS ON)
    include(CTest)
endif()

# add_subdirectory(extern)
# add_subdirectory(library)
add_subdirectory(main)