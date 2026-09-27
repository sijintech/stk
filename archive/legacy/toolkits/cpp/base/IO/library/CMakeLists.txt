# set(HEADER_LIST "${PROJECT_SOURCE_DIR}/include/nmathbasic/nmathbasic.h")

set(C_OPT "")
set(libname io)

if(WIN32)
    set(LINK_OPT "Shlwapi")
    list(APPEND C_OPT "-D_CRT_SECURE_NO_WARNINGS")

    if(CMAKE_C_COMPILER_ID STREQUAL "ICL")
        list(APPEND C_OPT "/Qdiag-disable:1478")
    endif()
else()
    set(LINK_OPT)
endif()

file(GLOB HEADER_LIST CONFIGURE_DEPENDS
    "${PROJECT_SOURCE_DIR}/include/niobasic/*.h")
file(GLOB F90_SRC_LIST CONFIGURE_DEPENDS "${PROJECT_SOURCE_DIR}/library/*.f90")
file(GLOB DAT_SRC_LIST CONFIGURE_DEPENDS
    "${PROJECT_SOURCE_DIR}/library/datFile/*.c"
    "${PROJECT_SOURCE_DIR}/library/datFile/*.f90")
file(GLOB DREAM_SRC_LIST CONFIGURE_DEPENDS
    "${PROJECT_SOURCE_DIR}/library/dream3DFile/*.c"
    "${PROJECT_SOURCE_DIR}/library/dream3DFile/*.f90")
file(GLOB CONTROL_SRC_LIST CONFIGURE_DEPENDS
    "${PROJECT_SOURCE_DIR}/library/controlFile/*.c"
    "${PROJECT_SOURCE_DIR}/library/controlFile/*.f90")
file(GLOB TIME_SRC_LIST CONFIGURE_DEPENDS
    "${PROJECT_SOURCE_DIR}/library/timeFile/*.c"
    "${PROJECT_SOURCE_DIR}/library/timeFile/*.f90")
file(GLOB VTI_SRC_LIST CONFIGURE_DEPENDS
    "${PROJECT_SOURCE_DIR}/library/vtiFile/*.c"
    "${PROJECT_SOURCE_DIR}/library/vtiFile/*.f90")
file(GLOB FIGURE_SRC_LIST CONFIGURE_DEPENDS
    "${PROJECT_SOURCE_DIR}/library/figureFile/*.c"
    "${PROJECT_SOURCE_DIR}/library/figureFile/*.f90")
file(GLOB PATH_SRC_LIST CONFIGURE_DEPENDS
    "${PROJECT_SOURCE_DIR}/library/path/*.c"
    "${PROJECT_SOURCE_DIR}/library/path/*.f90")

list(
    APPEND
    SRC_LIST
    ${PATH_SRC_LIST}
    ${FIGURE_SRC_LIST}
    ${DAT_SRC_LIST}
    ${CONTROL_SRC_LIST}
    ${TIME_SRC_LIST}
    ${VTI_SRC_LIST}
    ${DREAM_SRC_LIST}
    ${F90_SRC_LIST})

add_library(${libname} STATIC)
add_library(mupro::${libname} ALIAS ${libname})
target_sources(${libname} PRIVATE ${SRC_LIST} ${HEADER_LIST})
set_property(TARGET ${libname} PROPERTY C_STANDARD 99)

find_package(LibXml2 REQUIRED)

target_compile_options(${libname} PUBLIC ${C_OPT}
) # $<TARGET_PROPERTY:MKL::MKL,INTERFACE_COMPILE_OPTIONS>)
target_include_directories(
    ${libname} PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include"
    ${CMAKE_CURRENT_BINARY_DIR} ${LIBXML2_INCLUDE_DIR})
target_link_libraries(${libname} PUBLIC LibXml2::LibXml2 zf_log mupro::text
    mupro::math ${LINK_OPT})

source_group(
    TREE "${PROJECT_SOURCE_DIR}/include"
    PREFIX "Header Files"
    FILES ${HEADER_LIST})
