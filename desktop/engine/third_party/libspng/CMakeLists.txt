# libspng 0.7.4 (BSD-2-Clause) built against miniz 3.0.2 (MIT) instead of zlib, so no system
# library is needed on any platform. See UPSTREAM.json. Pure CPU; used by stk_io PNG I/O only.
add_library(stk_spng STATIC spng/spng.c miniz/miniz.c)
target_include_directories(stk_spng SYSTEM PUBLIC ${CMAKE_CURRENT_LIST_DIR}/spng
                                           PRIVATE ${CMAKE_CURRENT_LIST_DIR}/miniz)
target_compile_definitions(stk_spng PUBLIC SPNG_STATIC
                                    PRIVATE SPNG_USE_MINIZ MINIZ_NO_STDIO MINIZ_NO_ARCHIVE_APIS MINIZ_NO_TIME)
set_target_properties(stk_spng PROPERTIES C_STANDARD 99 POSITION_INDEPENDENT_CODE ON)
if(MSVC)
  target_compile_options(stk_spng PRIVATE /W0)
  target_compile_definitions(stk_spng PRIVATE _CRT_SECURE_NO_WARNINGS)
else()
  target_compile_options(stk_spng PRIVATE -w)
  if(NOT WIN32)
    find_library(STK_LIBM m)
    if(STK_LIBM)
      target_link_libraries(stk_spng PRIVATE ${STK_LIBM})
    endif()
  endif()
endif()
