set(EXE_NAME slab)

file(GLOB MAIN_SRC CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/*.c")

add_executable(${EXE_NAME} ${MAIN_SRC})

target_link_libraries(${EXE_NAME} PUBLIC  nstructuregenerator )
# target_include_directories(${EXE_NAME} PUBLIC ${PROJECT_SOURCE_DIR}/include )

install(TARGETS ${EXE_NAME} DESTINATION ${CMAKE_BINARY_DIR}/../bin)

configure_file("slab.xml" "slab.xml" COPYONLY)