# SPDX-License-Identifier: GPL-2.0-or-later
# cmake -DINPUT=<file> -DOUTPUT=<file.inc> -DNAME=<identifier> -P embed_file.cmake
# Writes `static const unsigned char NAME[] = {...}; static const size_t NAME_size = N;`
# (a byte array: MSVC limits string literals to 16 KiB).
file(READ "${INPUT}" _hex HEX)
string(LENGTH "${_hex}" _len)
math(EXPR _size "${_len} / 2")
string(REGEX REPLACE "([0-9a-f][0-9a-f])" "0x\\1," _bytes "${_hex}")
string(REGEX REPLACE "((0x[0-9a-f][0-9a-f],){32})" "\\1\n" _bytes "${_bytes}")
file(WRITE "${OUTPUT}.tmp"
  "/* Generated from ${INPUT} by embed_file.cmake; do not edit. */\n"
  "static const unsigned char ${NAME}[] = {\n${_bytes}0x00};\n"
  "static const size_t ${NAME}_size = ${_size};\n")
file(COPY_FILE "${OUTPUT}.tmp" "${OUTPUT}" ONLY_IF_DIFFERENT)
file(REMOVE "${OUTPUT}.tmp")
