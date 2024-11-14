cmake_minimum_required(VERSION 3.9...3.15)
if(${CMAKE_VERSION} VERSION_LESS 3.12)
  cmake_policy(VERSION ${CMAKE_MAJOR_VERSION}.${CMAKE_MINOR_VERSION})
else()
endif()
message(STATUS "CMake version is " ${CMAKE_MAJOR_VERSION}.${CMAKE_MINOR_VERSION})



# parameter setup
set(CMAKE_VERBOSE_MAKEFILE TRUE CACHE BOOL "Show compiling commands")
set(CMAKE_INSTALL_PREFIX "$ENV{HOME}/mupro" CACHE STRING "The install prefix for mupro ferroelectric module")
set(mupro_path "/gpfs/group/lqc3/default/mupro" CACHE STRING "The root directory of mupro library")
set(mupro_auto_choose TRUE CACHE BOOL "Based on the build type and compiler id, automatically determine the folder where mupro library is" FORCE)





# Don't change things below, if you are not sure what it is doing
set(exe_name muStructure)
project(
  ${exe_name}
  VERSION 1.1
  DESCRIPTION "The mupro structure generator main program, using the mupro phase-field library."
  LANGUAGES Fortran
)

set(compiler_id "Intel" CACHE STRING "Choose the type of compiler you're using." FORCE)
set_property(CACHE compiler_id PROPERTY STRINGS "Intel" "GNU")

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  message(STATUS "Setting the build type, default is Release")
  set(CMAKE_BUILD_TYPE "Debug" CACHE STRING "Choose the type of build." FORCE)
  set_property(CACHE CMAKE_BUILD_TYPE PROPERTY STRINGS "Debug" "Release" "MinSizeRel" "RelWithDebInfo")
endif()

set(CMAKE_INSTALL_PREFIX ${CMAKE_INSTALL_PREFIX}/${compiler_id}_${CMAKE_BUILD_TYPE})

if(${CMAKE_Fortran_COMPILER_ID} STREQUAL "Intel")
  set(CMAKE_Fortran_COMPILER "mpiifort" CACHE STRING "The fortran compiler" FORCE)
  set(fftw_lib "/gpfs/group/lqc3/default/fftw/lib" CACHE STRING "The library path of fftw")
  set(math_lib "/opt/intel/compilers_and_libraries_2016.3.210/linux/mkl" CACHE STRING "The library path for mkl")

  set(math_libs
    ${math_lib}/lib/intel64/libmkl_lapack95_ilp64.a
    ${math_lib}/lib/intel64/libmkl_scalapack_ilp64.a
    -Wl,--start-group
    ${math_lib}/lib/intel64/libmkl_intel_lp64.a
    ${math_lib}/lib/intel64/libmkl_sequential.a
    ${math_lib}/lib/intel64/libmkl_core.a
    ${math_lib}/lib/intel64/libmkl_blacs_intelmpi_ilp64.a
    -Wl,--end-group
    -lpthread -liomp5 -lm -ldl
    )
  message(STATUS "The mpi compiler" ${CMAKE_Fortran_COMPILER})
endif()

set(curl_lib /opt/aci/sw/python/3.6.3_anaconda-5.0.1/lib CACHE STRING "The directory of libcurl.a")

include(GNUInstallDirs)
if(${mupro_auto_choose})
  set(mupro_include ${mupro_path}/${compiler_id}_${CMAKE_BUILD_TYPE}/${CMAKE_INSTALL_INCLUDEDIR}) 
  set(mupro_lib ${mupro_path}/${compiler_id}_${CMAKE_BUILD_TYPE}/${CMAKE_INSTALL_LIBDIR}) 
else()
  set(mupro_include ${mupro_path}/${CMAKE_INSTALL_INCLUDEDIR}) 
  set(mupro_lib ${mupro_path}/${CMAKE_INSTALL_LIBDIR}) 
endif()

find_package(MPI)
#if(NOT TARGET MPI::MPI_Fortran)
  #add_library(MPI::MPI_Fortran IMPORTED INTERFACE)
  #set_property(TARGET MPI::MPI_Fortran PROPERTY INTERFACE_COMPILE_OPTIONS ${MPI_Fortran_COMPILE_FLAGS})
  #set_property(TARGET MPI::MPI_Fortran PROPERTY INTERFACE_INCLUDE_DIRECTORIES ${MPI_Fortran_INCLUDE_PATH})
  #set_property(TARGET MPI::MPI_Fortran PROPERTY INTERFACE_LINK_LIBRARIES ${MPI_Fortran_LINK_FLAGS} ${MPI_Fortran_LIBRARIES})
#endif()

message(STATUS mpilibrary ${MPI_Fortran_LIBRARIES} " " ${MPI_Fortran_LINK_FLAGS})

add_executable(
  ${exe_name}
  structureGenerator.f90
)

set_target_properties(
  ${exe_name}
  PROPERTIES
  LINKER_LANGUAGE Fortran
)  

target_include_directories(
  ${exe_name}
  PRIVATE
  ${MPI_Fortran_INCLUDE_PATH}
  ${mupro_include}
)


target_compile_options(
  ${exe_name}
  PRIVATE
  $<$<AND:$<CONFIG:Debug>,$<COMPILE_LANG_AND_ID:Fortran,Intel>>:-O0 -check bounds -g -traceback>
  $<$<AND:$<CONFIG:Release>,$<COMPILE_LANG_AND_ID:Fortran,Intel>>:-O3 -xSSE3 -align rec16byte >
  $<$<AND:$<CONFIG:Release>,$<COMPILE_LANG_AND_ID:Fortran,Intel>>:-align array64byte >
  $<$<AND:$<CONFIG:Release>,$<COMPILE_LANG_AND_ID:Fortran,Intel>>:-align all >
  )

add_definitions(-DCURL_STATICLIB)
find_package(CURL)

target_link_directories(
  ${exe_name}
  PUBLIC
  ${CURL_LIBRARYIES}
)

target_link_libraries(
  ${exe_name}
  PUBLIC
  ${mupro_lib}/libmupro.a
  ${fftw_lib}/libfftw3_mpi.a
  ${fftw_lib}/libfftw3.a
  ${math_libs}
  -lcurl -lssl -lcrypto
  #${curl_lib}/libcurl.a 
  #${curl_lib}/libssl.a 
  #${curl_lib}/libcrypto.a
  -lz -ldl -lstdc++ -static-libgcc
  #MPI::MPI_Fortran
  #${MPI_Fortran_LIBRARIES}
  )


install(
  TARGETS ${exe_name}
  EXPORT ${exe_name}Config
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
  ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
  RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)

file(GLOB mod_files ${PROJECT_BINARY_DIR}/*.mod)
install(
  FILES ${mod_files}
  DESTINATION ${CMAKE_INSTALL_BINDIR}
)

export(TARGETS ${exe_name} FILE ${exe_name}Config.cmake)
