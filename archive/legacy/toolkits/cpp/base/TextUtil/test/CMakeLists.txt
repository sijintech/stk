include(FetchContent)
if(${CMAKE_VERSION} VERSION_LESS 3.14)
  include(cmake/add_FetchContent_MakeAvailable.cmake)
endif()

FetchContent_Declare(
  unity
  GIT_REPOSITORY https://github.com/ThrowTheSwitch/Unity.git
  GIT_TAG v2.5.2)
FetchContent_MakeAvailable(unity)


add_executable(test_char test_char.c)
target_link_libraries(test_char PRIVATE ntextutils unity)
add_test(NAME test_char COMMAND test_char) # Command can be a target

add_executable(test_hex test_hex.c)
target_link_libraries(test_hex PRIVATE ntextutils unity)
add_test(NAME test_hex COMMAND test_hex) # Command can be a target