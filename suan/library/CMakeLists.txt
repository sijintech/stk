cmake_minimum_required(VERSION 3.0)
if (POLICY CMP0025)
  cmake_policy(SET CMP0025 NEW)
endif ()
set (CMAKE_CXX_STANDARD 11)

project(mupro-utility-library)
if (${CMAKE_SYSTEM_NAME} MATCHES "Windows")
    set(WINDOWS TRUE)
elseif (${CMAKE_SYSTEM_NAME} MATCHES "Linux")
    set(LINUX TRUE)
elseif (${CMAKE_SYSTEM_NAME} MATCHES "Darwin")
    set(MACOSX TRUE)
endif()

#if(APPLE)

#elseif(WIN32)

#else(LINUX)
#set (VTK_DIR
#   /gpfs/group/lqc3/default/VTK-static/lib/cmake/vtk-8.0
#   )
set (CMAKE_BUILD_TYPE
    Release
    )

#endif()


set (CMAKE_ARCHIVE_OUTPUT_DIRECTORY
    ${CMAKE_CURRENT_SOURCE_DIR}/../lib)

find_package(HDF5 REQUIRED)
find_package(VTK)



file(GLOB CXX *.cxx)
file(GLOB HPP *.hpp)
file(GLOB H *.h)
#vtk_module_config(VTK
#  vtkCommonCore
#  vtkIOImage
#  vtkIOXML
#  vtkInteractionWidgets
#  vtkFiltersGeometry
#  vtkRendering${VTK_RENDERING_BACKEND}
#  vtkRenderingVolume${VTK_RENDERING_BACKEND}
#)
#include(${VTK_USE_FILE})
include_directories(${CMAKE_CURRENT_SOURCE_DIR})

add_library( MUtil STATIC ${CXX} )
