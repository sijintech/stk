set(EXE_NAME effprop)

set(INCLUDE_DIR
    "${PROJECT_SOURCE_DIR}/include"
    ${nlicense_mod_dir}
    ${nmathfft_mod_dir}
    ${niobasic_mod_dir}
    ${nstructuregenerator_mod_dir}
    ${ntextutils_mod_dir}
    ${zf_log_mod_dir})
set(LINK_OPT "")

if(WIN32)
  set(C_OPT "/Wno-unused-variable" "/Wno-unused-but-set-variable")
  list(APPEND C_OPT "-D_CRT_SECURE_NO_WARNINGS")

  if(CMAKE_C_COMPILER_ID STREQUAL "ICL")
    list(APPEND C_OPT "/Qdiag-disable:1478")
  endif()
else()
  set(C_OPT)
endif()

file(
  GLOB
  MAIN_SRC
  CONFIGURE_DEPENDS
  "${PROJECT_SOURCE_DIR}/main/*.c"
  "${PROJECT_SOURCE_DIR}/main/dielectric/*.c"
  "${PROJECT_SOURCE_DIR}/main/diffusion/*.c"
  "${PROJECT_SOURCE_DIR}/main/elastic/*.c"
  "${PROJECT_SOURCE_DIR}/main/electrical/*.c"
  "${PROJECT_SOURCE_DIR}/main/magnetic/*.c"
  "${PROJECT_SOURCE_DIR}/main/initialize_destruct/*.c"
  "${PROJECT_SOURCE_DIR}/main/load_input/*.c"
  "${PROJECT_SOURCE_DIR}/main/magnetoelectric/*.c"
  "${PROJECT_SOURCE_DIR}/main/piezoelectric/*.c"
  "${PROJECT_SOURCE_DIR}/main/piezomagnetic/*.c"
  "${PROJECT_SOURCE_DIR}/main/thermal/*.c")

# include(${PROJECT_SOURCE_DIR}/cmake/PrepareFFTW.cmake)
add_executable(${EXE_NAME} ${MAIN_SRC})
set_property(TARGET ${EXE_NAME} PROPERTY C_STANDARD 99)
set_target_properties(${EXE_NAME} PROPERTIES LINKER_LANGUAGE C)

message(STATUS the system is ${CMAKE_SYSTEM_NAME})

# if(${CMAKE_SYSTEM_NAME} MATCHES "Darwin")
#   message(STATUS loading more rpath ${CMAKE_INSTALL_RPATH})
#   set_property(TARGET ${EXE_NAME} PROPERTY INSTALL_RPATH_USE_LINK_PATH True)
#   set_property(
#     TARGET ${EXE_NAME}
#     PROPERTY
#       INSTALL_RPATH "@loader_path/../lib"
#       "/opt/intel/oneapi/compiler/2022.0.0/mac/bin/intel64/../../compiler/lib"
#       "/opt/intel/oneapi/mkl/latest/lib")
# endif()

target_compile_options(${EXE_NAME} PUBLIC ${C_OPT}
)# $<TARGET_PROPERTY:MKL::MKL,INTERFACE_COMPILE_OPTIONS>)

# target_link_directories(${EXE_NAME} PUBLIC ${FFTW_LIB})
target_link_libraries(
  ${EXE_NAME}
  PUBLIC mupro::license
         mupro::math
         mupro::fft
         mupro::io
         mupro::text
         zf_log
         mupro::structure
         mupro::material
         ${LINK_OPT})
target_include_directories(${EXE_NAME} PUBLIC ${INCLUDE_DIR})
DebugSetup(TARGET ${EXE_NAME})
# target_link_directories(${EXE_NAME} PUBLIC ${FFTW_LIB})

install(TARGETS ${EXE_NAME} DESTINATION ${CMAKE_BINARY_DIR}/../bin)

configure_file("input.xml" "input.xml" COPYONLY)
configure_file("secret" "secret" COPYONLY)
configure_file("microstructure.in" "microstructure.in" COPYONLY)
