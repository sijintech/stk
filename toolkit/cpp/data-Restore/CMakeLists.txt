cmake_minimum_required(VERSION 3.3 FATAL_ERROR)
if (POLICY CMP0025)
  cmake_policy(SET CMP0025 NEW)
endif ()
set (CMAKE_CXX_STANDARD 11)



project (DomainRendering)
if (${CMAKE_SYSTEM_NAME} MATCHES "Windows")
    set(WINDOWS TRUE)
elseif (${CMAKE_SYSTEM_NAME} MATCHES "Linux")
    set(LINUX TRUE)
elseif (${CMAKE_SYSTEM_NAME} MATCHES "Darwin")
    set(MACOSX TRUE)
endif()
find_package(HDF5)

if(MACOSX)

elseif(WINDOWS)

else(LINUX)
set (CMAKE_BUILD_TYPE
    Release
    )

endif()
#


set(BACKUP_SRCS
    ferroRestore
)

set (EXECUTABLE_OUTPUT_PATH
    ${CMAKE_CURRENT_SOURCE_DIR}/../bin/
    )


include_directories(
    ${CMAKE_CURRENT_BINARY_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/../MUtil/
    ${HDF5_INCLUDE_DIR}
    )

MESSAGE(STATUS "directory " ${CMAKE_SOURCE_DIR})
MESSAGE(STATUS "directory " ${CMAKE_CURRENT_SOURCE_DIR})

foreach(name ${BACKUP_SRCS})
    # add_executable(${name} MACOSX_BUNDLE ${name}.cxx) # ${SRCS} ${HDRS}) */
    add_executable(${name} ${name}.cxx) # ${SRCS} ${HDRS})
    set(mutil ${CMAKE_CURRENT_SOURCE_DIR}/../lib/libMUtil.a)
    #target_link_libraries(HDF5IO IO)
    target_link_libraries(${name} hdf5 hdf5_hl ${mutil})
endforeach()



