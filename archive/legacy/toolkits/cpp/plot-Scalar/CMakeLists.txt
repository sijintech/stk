cmake_minimum_required(VERSION 3.3 FATAL_ERROR)
if (POLICY CMP0025)
    cmake_policy(SET CMP0025 NEW)
endif ()
set (CMAKE_CXX_STANDARD 11)



project (VolumeRendering)
if (${CMAKE_SYSTEM_NAME} MATCHES "Windows")
    set(WINDOWS TRUE)
elseif (${CMAKE_SYSTEM_NAME} MATCHES "Linux")
    set(LINUX TRUE)
elseif (${CMAKE_SYSTEM_NAME} MATCHES "Darwin")
    set(MACOSX TRUE)
endif()

if(MACOSX)

elseif(WINDOWS)

else(LINUX)
    set (VTK_DIR
        /gpfs/group/lqc3/default/VTK-static/lib/cmake/vtk-8.0
        )

    #set (CMAKE_CXX_COMPILER
    #    /opt/rh/devtoolset-4/root/usr/bin/c++
    #  )
    #
    #set (CMAKE_C_COMPILER
    #    /opt/rh/devtoolset-4/root/usr/bin/gcc
    #  )
    #
    set (CMAKE_BUILD_TYPE
        Release
        )

endif()
#
#
find_package(VTK REQUIRED)
include(${VTK_USE_FILE})
message( STATUS "vtk fiel" ${VTK_USE_FILE})
vtk_module_config(VTK
    vtkCommonCore
    vtkIOImage
    vtkIOXML
    vtkInteractionWidgets
    vtkRenderingVolume${VTK_RENDERING_BACKEND}
    #vtkRendering${VTK_RENDERING_BACKEND}
    )

MESSAGE(STATUS "backend" ${VTK_RENDERING_BACKEND})

set(RENDERING_EXAMPLES_SRCS
    ScalarVTK
    #/* FixedPointVolumeRayCastMapperCT */
    #/* GPURenderDemo */
    )

set (EXECUTABLE_OUTPUT_PATH
    ${CMAKE_CURRENT_SOURCE_DIR}/../bin/
    )

include(${VTK_USE_FILE})

include_directories(
    ${CMAKE_CURRENT_BINARY_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/../IO/
    )



foreach(name ${RENDERING_EXAMPLES_SRCS})
    add_executable(${name} MACOSX_BUNDLE ${name}.cxx)# ${SRCS} ${HDRS})
    target_link_libraries(${name} ${VTK_LIBRARIES})
    target_link_libraries(${name} ${CMAKE_CURRENT_SOURCE_DIR}/../IO/libIO.a)
endforeach()



