cmake_minimum_required(VERSION 3.12)


set(PJ_NAME nstructuregenerator)

project(
    ${PJ_NAME}
    VERSION 0.1.3 
    DESCRIPTION "The mupro structure generator module"
    LANGUAGES C CXX Fortran
)


# add_subdirectory(extern)
add_subdirectory(library)

if(CMAKE_PROJECT_NAME STREQUAL PROJECT_NAME)
    set(CMAKE_CXX_EXTENSIONS OFF)
    set_property(GLOBAL PROPERTY USE_FOLDERS ON)
    include(CTest)
    add_subdirectory(main)
endif()