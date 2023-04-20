FetchContent_Declare(
  unity
  GIT_REPOSITORY https://github.com/ThrowTheSwitch/Unity.git
  GIT_TAG v2.5.2)
FetchContent_MakeAvailable(unity)

# add_executable(test1 test.c)
# target_compile_features(test1 PRIVATE cxx_std_17)

# target_link_libraries(test1 PRIVATE nmathbasic unity)

# add_test(NAME test1 COMMAND test1) # Command can be a target