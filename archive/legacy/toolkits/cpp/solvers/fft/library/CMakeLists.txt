cmake_policy(SET CMP0079 NEW)

set(INCLUDE_DIR  ${nmathbasic_mod_dir})
set(C_OPT "")
set(LINK_OPT "")

file(GLOB HEADER_LIST CONFIGURE_DEPENDS "${PROJECT_SOURCE_DIR}/include/nmathfft/*.h")
file(GLOB LIB_C_SRC CONFIGURE_DEPENDS 
"${PROJECT_SOURCE_DIR}/library/*.c" 
"${PROJECT_SOURCE_DIR}/library/fft/*.c" 
"${PROJECT_SOURCE_DIR}/library/cahnhilliard/*.c" 
"${PROJECT_SOURCE_DIR}/library/elastic/*.c"
"${PROJECT_SOURCE_DIR}/library/poisson/*.c")

file(GLOB LIB_F_SRC CONFIGURE_DEPENDS 
"${PROJECT_SOURCE_DIR}/library/*.f90" 
"${PROJECT_SOURCE_DIR}/library/fft/*.f90")
if(NOT TARGET MKL::MKL)
find_package(MKL CONFIG REQUIRED)
endif()
list(APPEND LIB_SRC ${LIB_C_SRC} ${LIB_F_SRC})

  if(WIN32)
    list(APPEND TEST_COPT "-D_CRT_SECURE_NO_WARNINGS")
    if (CMAKE_${TEST_LANG}_COMPILER_ID STREQUAL "ICL")
      list(APPEND TEST_COPT "/Qdiag-disable:1478")
    endif()
  endif()

# include(${PROJECT_SOURCE_DIR}/cmake/PrepareFFTW.cmake)
# include(${PROJECT_SOURCE_DIR}/cmake/PrepareMPI.cmake)

set(libname fft)
add_library(${libname} STATIC)
add_library(mupro::${libname} ALIAS ${libname})
target_sources(${libname} PRIVATE ${LIB_SRC} ${HEADER_LIST})
set_property(TARGET ${libname} PROPERTY C_STANDARD 99)

# MESSAGE(STATUS  ${MKL_INCLUDE}/fftw )
target_include_directories(${libname} PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include ${CMAKE_CURRENT_BINARY_DIR} ${MKL_INCLUDE}/fftw $<TARGET_PROPERTY:MKL::MKL,INTERFACE_INCLUDE_DIRECTORIES>)
target_compile_options(${libname} PUBLIC ${C_OPT} $<TARGET_PROPERTY:MKL::MKL,INTERFACE_COMPILE_OPTIONS>)
# target_link_directories(${LIB_NAME} PUBLIC )
#if(${CMAKE_SYSTEM_NAME} MATCHES "Windows")
#target_link_libraries(${LIB_NAME} PUBLIC fftw3-3 mkl_core fftw3)
#else()
#target_link_libraries(${LIB_NAME} PUBLIC fftw3)
#endif()
target_link_libraries(${libname} PUBLIC zf_log mupro::math mupro::text mupro::io mupro::structure ${LINK_OPT} $<LINK_ONLY:MKL::MKL> )

# target_compile_features(${LIB_NAME} PUBLIC cxx_std_11)

source_group(
    TREE "${PROJECT_SOURCE_DIR}/include"
    PREFIX "Header Files"
    FILES ${HEADER_LIST}
)