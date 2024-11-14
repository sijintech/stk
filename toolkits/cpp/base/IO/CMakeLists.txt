cmake_minimum_required(VERSION 3.12)


get_project_version(NIOBASIC library/include/niobasic/niobasic.h)

project(
  niobasic
  VERSION
    ${PROJECT_VERSION_MAJOR}.${PROJECT_VERSION_MINOR}.${PROJECT_VERSION_PATCH}
  DESCRIPTION "The basic input and output utilities"
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
  add_subdirectory(tests)
endif()
