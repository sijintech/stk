# set(HEADER_LIST "${PROJECT_SOURCE_DIR}/include/nmathbasic/nmathbasic.h")

# set(INCLUDE_DIR "${PROJECT_SOURCE_DIR}/include" "${ntextutils_include_dir}")
set(C_OPT "")
set(LINK_OPT "")
set(libname math)
cmake_policy(SET CMP0079 NEW)
# find_package(MKL CONFIG REQUIRED)

if(WIN32)
    list(APPEND C_OPT "-D_CRT_SECURE_NO_WARNINGS")

    if(CMAKE_C_COMPILER_ID STREQUAL "ICL")
        list(APPEND C_OPT "/Qdiag-disable:1478")
    endif()
endif()

file(GLOB HEADER_LIST CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/include/nmathbasic/*.h" "${CMAKE_CURRENT_SOURCE_DIR}/include/nmathbasic/exprtk.hpp")
file(GLOB ARRAY_SRC_LIST CONFIGURE_DEPENDS "${PROJECT_SOURCE_DIR}/library/array/*.c" "${PROJECT_SOURCE_DIR}/library/array/*.f90")
file(GLOB CONSTANT_SRC_LIST CONFIGURE_DEPENDS "${PROJECT_SOURCE_DIR}/library/constant/*.c" "${PROJECT_SOURCE_DIR}/library/constant/*.f90")

# file(GLOB DECOMPOSE_SRC_LIST CONFIGURE_DEPENDS "${PROJECT_SOURCE_DIR}/library/decompose/*.c")
file(GLOB EXPRESSION_SRC_LIST CONFIGURE_DEPENDS "${PROJECT_SOURCE_DIR}/library/expression/*.cpp")

# file(GLOB FILTER_SRC_LIST CONFIGURE_DEPENDS "${PROJECT_SOURCE_DIR}/library/filter/*.c")
# file(GLOB LAPACK_SRC_LIST CONFIGURE_DEPENDS "${PROJECT_SOURCE_DIR}/library/lapack/*.f")
file(GLOB TENSOR_SRC_LIST CONFIGURE_DEPENDS "${PROJECT_SOURCE_DIR}/library/tensor/*.c")
file(GLOB TRANSFORMATION_SRC_LIST CONFIGURE_DEPENDS "${PROJECT_SOURCE_DIR}/library/transformation/*.c")
file(GLOB VECTOR_SRC_LIST CONFIGURE_DEPENDS "${PROJECT_SOURCE_DIR}/library/vector/*.c")
list(APPEND SRC_LIST "${PROJECT_SOURCE_DIR}/library/random.c" "${PROJECT_SOURCE_DIR}/library/nmathbasic.f90" ${ARRAY_SRC_LIST} ${CONSTANT_SRC_LIST} ${EXPRESSION_SRC_LIST} ${FILTER_SRC_LIST} ${TENSOR_SRC_LIST} ${TRANSFORMATION_SRC_LIST} ${VECTOR_SRC_LIST}) # ${LAPACK_SRC_LIST})

message(STATUS ${SRC_LIST})
add_library(${libname} STATIC)
add_library(mupro::${libname} ALIAS ${libname})
target_sources(${libname} PRIVATE ${SRC_LIST} ${HEADER_LIST})
set_property(TARGET ${libname} PROPERTY C_STANDARD 99)

target_include_directories(${libname} PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include ${CMAKE_CURRENT_BINARY_DIR} )#$<TARGET_PROPERTY:MKL::MKL,INTERFACE_INCLUDE_DIRECTORIES>)
target_compile_options(${libname} PUBLIC ${C_OPT} )#$<TARGET_PROPERTY:MKL::MKL,INTERFACE_COMPILE_OPTIONS>)
target_link_libraries(${libname} PUBLIC zf_log mupro::text ${LINK_OPT} )#$<LINK_ONLY:MKL::MKL>)

# if(NOT ${CMAKE_CXX_COMPILER_ID} STREQUAL Intel)
# target_compile_features(nmathbasic PUBLIC cxx_std_11)
# endif()
# if(${CMAKE_SYSTEM_NAME} MATCHES "Windows")
# target_compile_options(${libname} PUBLIC -Wa,-mbig-obj)
# endif()
source_group(
    TREE "${PROJECT_SOURCE_DIR}/library/include"
    PREFIX "Header Files"
    FILES ${HEADER_LIST}
)