# nlohmann/json 3.12.0 (MIT), single-header amalgamation. See UPSTREAM.json.
add_library(stk_nlohmann_json INTERFACE)
target_include_directories(stk_nlohmann_json SYSTEM INTERFACE ${CMAKE_CURRENT_LIST_DIR}/include)
target_compile_features(stk_nlohmann_json INTERFACE cxx_std_20)
if(NOT TARGET nlohmann_json::nlohmann_json)
  add_library(nlohmann_json::nlohmann_json ALIAS stk_nlohmann_json)
endif()
