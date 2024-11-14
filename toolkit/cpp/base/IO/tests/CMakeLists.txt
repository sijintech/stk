include(FetchContent)
# FetchContent_MakeAvailable was not added until CMake 3.14; use our shim
if(${CMAKE_VERSION} VERSION_LESS 3.14)
  include(cmake/add_FetchContent_MakeAvailable.cmake)
endif()

FetchContent_Declare(
  unity
  GIT_REPOSITORY https://github.com/ThrowTheSwitch/Unity.git
  GIT_TAG v2.5.2)
FetchContent_MakeAvailable(unity)

# add_executable(test_xml test_xml.c)
# target_link_libraries(test_xml PRIVATE niobasic unity)

# add_executable(test_vtk test_vtk.c)
# target_link_libraries(test_vtk PRIVATE niobasic unity)


# add_test(NAME test_xml COMMAND test_xml) # Command can be a target
# add_test(NAME test_vtk COMMAND test_vtk) # Command can be a target