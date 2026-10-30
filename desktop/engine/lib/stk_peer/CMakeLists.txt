# SPDX-License-Identifier: MIT
# Explicit MIT exception to the desktop/ default; see LICENSE and README.md.
cmake_minimum_required(VERSION 3.20)
if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
  project(stk_peer_transport LANGUAGES CXX)
endif()
# Dependencies are provisioned separately. This module never downloads a network stack.
find_package(LibDataChannel 0.24.6 EXACT CONFIG REQUIRED)
find_package(OpenSSL 3 REQUIRED COMPONENTS Crypto)
find_package(Threads REQUIRED)
if(NOT TARGET nlohmann_json::nlohmann_json)
  add_subdirectory("${CMAKE_CURRENT_LIST_DIR}/../../third_party/nlohmann_json"
                   "${CMAKE_CURRENT_BINARY_DIR}/nlohmann_json")
endif()
add_executable(stk-peer-transport src/main.cc)
target_compile_features(stk-peer-transport PRIVATE cxx_std_20)
target_link_libraries(stk-peer-transport PRIVATE LibDataChannel::LibDataChannel
                      OpenSSL::Crypto Threads::Threads nlohmann_json::nlohmann_json)
if(MSVC)
  target_compile_options(stk-peer-transport PRIVATE /utf-8 /W4)
else()
  target_compile_options(stk-peer-transport PRIVATE -Wall -Wextra -Wpedantic)
endif()
# No install rule: top-level packaging must opt in and carry all dependency notices.

option(STK_PEER_BUILD_TEST_PEER "Build the uninstalled adversarial partial-frame test peer" OFF)
if(STK_PEER_BUILD_TEST_PEER)
  add_executable(stk-peer-partial-test tests/partial_peer.cc)
  target_compile_features(stk-peer-partial-test PRIVATE cxx_std_20)
  target_link_libraries(stk-peer-partial-test PRIVATE LibDataChannel::LibDataChannel
                        OpenSSL::Crypto Threads::Threads)
endif()
