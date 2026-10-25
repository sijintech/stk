# SPDX-License-Identifier: GPL-2.0-or-later
# CPU-only proof of the real guardedalloc/static-destruction gate in the opt-in harness.
if(NOT DEFINED PROGRAM OR NOT MODE MATCHES "^(late-static|leak|early-failure)$")
  message(FATAL_ERROR "PROGRAM and a valid memory-gate MODE are required")
endif()
set(ENV{STK_TOKEN_PLAN_API_KEY} "")
unset(ENV{STK_TOKEN_PLAN_MODEL})
# Invoke directly: an intermediate env launcher can collapse a child signal into exit 1.
execute_process(
  COMMAND "${PROGRAM}" --memory-gate-selftest "${MODE}"
  TIMEOUT 20 RESULT_VARIABLE _status OUTPUT_VARIABLE _stdout ERROR_VARIABLE _stderr)
set(_output "${_stdout}\n${_stderr}")
set(_expected 1)
if(MODE STREQUAL "late-static")
  set(_expected 0)
endif()
# Crashes, signals, timeout/error strings, skip 77 and CLI 2 must all fail this test.
if(NOT "${_status}" STREQUAL "${_expected}")
  message(FATAL_ERROR "${MODE}: expected exact exit ${_expected}, received '${_status}'\n${_output}")
endif()
set(_required
  "self-test: late guarded static constructed after gate registration"
  "self-test: late guarded static destroyed before final gate")
set(_forbidden "PASS: native document evidence" "PASS: document preview" "Error: Not freed memory blocks")
if(MODE STREQUAL "leak")
  list(APPEND _required "self-test: deliberate 64-byte guarded leak allocated"
    "ok: guarded self-test static remains live after Runtime"
    "guardedalloc: final blocks=1 bytes=64 after engine static destruction"
    "stk-document-preview-spike deliberate self-test leak"
    "FAIL: guarded STK allocations remain after engine static destruction")
  list(APPEND _forbidden "ok: no guarded STK allocation leaks" "final zero does not override")
else()
  list(APPEND _required "guardedalloc: final blocks=0 bytes=0 after engine static destruction")
  if(MODE STREQUAL "late-static")
    list(APPEND _required "ok: guarded self-test static remains live after Runtime"
      "ok: no guarded STK allocation leaks after engine static destruction")
    list(APPEND _forbidden "FAIL:" "final zero does not override")
  else()
    list(APPEND _required "FAIL: controlled early memory-gate self-test failure"
      "guardedalloc: final zero does not override earlier run failure")
    list(APPEND _forbidden "ok: no guarded STK allocation leaks")
  endif()
endif()
foreach(_marker IN LISTS _required)
  string(FIND "${_output}" "${_marker}" _found)
  if(_found EQUAL -1)
    message(FATAL_ERROR "${MODE}: missing '${_marker}'\n${_output}")
  endif()
endforeach()
foreach(_marker IN LISTS _forbidden)
  string(FIND "${_output}" "${_marker}" _found)
  if(NOT _found EQUAL -1)
    message(FATAL_ERROR "${MODE}: forbidden '${_marker}'\n${_output}")
  endif()
endforeach()
# Both markers use stdout: also prove destruction preceded the final allocator snapshot.
string(FIND "${_stdout}" "self-test: late guarded static destroyed before final gate" _destroyed)
string(FIND "${_stdout}" "guardedalloc: final blocks=" _checked)
if(NOT _destroyed LESS _checked)
  message(FATAL_ERROR "${MODE}: allocator was checked before the late static was destroyed\n${_output}")
endif()
message(STATUS "memory gate ${MODE}: exact exit ${_expected} and required diagnostics verified")
