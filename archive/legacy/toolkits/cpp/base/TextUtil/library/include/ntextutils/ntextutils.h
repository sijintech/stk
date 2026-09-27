#ifndef __NTEXTUTILS_H__
#define __NTEXTUTILS_H__

#define NTEXTUTILS_VERSION_MAJOR 0
#define NTEXTUTILS_VERSION_MINOR 1
#define NTEXTUTILS_VERSION_PATCH 0
#define NTEXTUTILS_VERSION                                                     \
    ((NTEXTUTILS_VERSION_MAJOR << 16) | (NTEXTUTILS_VERSION_MINOR << 8) |      \
     NTEXTUTILS_VERSION_PATCH)

#define MAX_STRING 2048
#define MAX_STRING_ARRAY 32
#define NAME_STRING 128
#define INFO_STRING 512

/* Define declarator for cross plateform support*/
#define NTEXTUTILSPUBFUN
#define NTEXTUTILSPUBVAR
#define NTEXTUTILSCALL
#define NTEXTUTILSCDECL

/* Windows platform with MS compiler */
#if defined(_WIN32) && defined(_MSC_VER)
#undef NTEXTUTILSPUBFUN
#undef NTEXTUTILSPUBVAR
#undef NTEXTUTILSCALL
#undef NTEXTUTILSCDECL
#if defined(IN_LIBNTEXTUTILS) && !defined(LIBNTEXTUTILS_STATIC)
#define NTEXTUTILSPUBFUN __declspec(dllexport)
#define NTEXTUTILSPUBVAR __declspec(dllexport)
#else
#define NTEXTUTILSPUBFUN
#if !defined(LIBNTEXTUTILS_STATIC)
#define NTEXTUTILSPUBVAR __declspec(dllimport) extern
#else
#define NTEXTUTILSPUBVAR extern
#endif
#endif
#if defined(LIBNTEXTUTILS_FASTCALL)
#define NTEXTUTILSCALL __fastcall
#else
#define NTEXTUTILSCALL __cdecl
#endif
#define NTEXTUTILSCDECL __cdecl
#endif

/* Windows platform with Borland compiler */
#if defined(_WIN32) && defined(__BORLANDC__)
#undef NTEXTUTILSPUBFUN
#undef NTEXTUTILSPUBVAR
#undef NTEXTUTILSCALL
#undef NTEXTUTILSCDECL
#if defined(IN_LIBNTEXTUTILS) && !defined(LIBNTEXTUTILS_STATIC)
#define NTEXTUTILSPUBFUN __declspec(dllexport)
#define NTEXTUTILSPUBVAR __declspec(dllexport) extern
#else
#define NTEXTUTILSPUBFUN
#if !defined(LIBNTEXTUTILS_STATIC)
#define NTEXTUTILSPUBVAR __declspec(dllimport) extern
#else
#define NTEXTUTILSPUBVAR extern
#endif
#endif
#define NTEXTUTILSCALL __cdecl
#define NTEXTUTILSCDECL __cdecl
#endif

/* Windows platform with GNU compiler (Mingw) */
#if defined(_WIN32) && defined(__MINGW32__)
#undef NTEXTUTILSPUBFUN
#undef NTEXTUTILSPUBVAR
#undef NTEXTUTILSCALL
#undef NTEXTUTILSCDECL
/*
 * if defined(IN_LIBNTEXTUTILS) this raises problems on mingw with msys
 * _imp__NTEXTUTILSFree listed as missing. Try to workaround the problem
 * by also making that declaration when compiling client code.
 */
#if defined(IN_LIBNTEXTUTILS) && !defined(LIBNTEXTUTILS_STATIC)
#define NTEXTUTILSPUBFUN __declspec(dllexport)
#define NTEXTUTILSPUBVAR __declspec(dllexport) extern
#else
#define NTEXTUTILSPUBFUN
#if !defined(LIBNTEXTUTILS_STATIC)
#define NTEXTUTILSPUBVAR __declspec(dllimport) extern
#else
#define NTEXTUTILSPUBVAR extern
#endif
#endif
#define NTEXTUTILSCALL __cdecl
#define NTEXTUTILSCDECL __cdecl
#endif

/* Cygwin platform (does not define _WIN32), GNU compiler */
#if defined(__CYGWIN__)
#undef NTEXTUTILSPUBFUN
#undef NTEXTUTILSPUBVAR
#undef NTEXTUTILSCALL
#undef NTEXTUTILSCDECL
#if defined(IN_LIBNTEXTUTILS) && !defined(LIBNTEXTUTILS_STATIC)
#define NTEXTUTILSPUBFUN __declspec(dllexport)
#define NTEXTUTILSPUBVAR __declspec(dllexport)
#else
#define NTEXTUTILSPUBFUN
#if !defined(LIBNTEXTUTILS_STATIC)
#define NTEXTUTILSPUBVAR __declspec(dllimport) extern
#else
#define NTEXTUTILSPUBVAR extern
#endif
#endif
#define NTEXTUTILSCALL __cdecl
#define NTEXTUTILSCDECL __cdecl
#endif

/* Compatibility */
#if !defined(LIBNTEXTUTILS_DLL_IMPORT)
#define LIBNTEXTUTILS_DLL_IMPORT NTEXTUTILSPUBVAR
#endif

#include "assert.h"
#include "stdarg.h"
#include "stdio.h"
#include "stdlib.h"
#include "string.h"
#include <time.h>
// #include <regex.h>
#ifdef __cplusplus
extern "C"
{
#endif

    typedef enum
    {
        NTEXTUTILS_ERR_GOOD = 0,
        NTEXTUTILS_ERR_UNKNOWNKEYWORD = 1,
        NTEXTUTILS_ERR_XMLFILEMISSING = 2,
        NTEXTUTILS_ERR_FILE_OK = 10,
        NTEXTUTILS_ERR_FILE_NOT_EXIST = 11,
        NTEXTUTILS_ERR_FILE_TO_LARGE = 12,
        NTEXTUTILS_ERR_FILE_READ_ERROR = 13
    } NTEXTUTILSError;

    typedef struct
    {
        size_t length;
        char data[MAX_STRING];
    } NString;
    typedef NString* NStringPtr;

    typedef struct
    {
        int length;
        char data[MAX_STRING_ARRAY][MAX_STRING];
    } NStringArray;
    typedef NStringArray* NStringArrayPtr;
    // String related functions
    NTEXTUTILSPUBFUN int NTEXTUTILSCALL n_char_exist(const char* base,
                                                     char comp);
    NTEXTUTILSPUBFUN int NTEXTUTILSCALL n_string_exist(const char* base,
                                                       const char* comp);
    NTEXTUTILSPUBFUN int NTEXTUTILSCALL n_string_count(const char* base,
                                                       const char* comp);
    NTEXTUTILSPUBFUN int NTEXTUTILSCALL n_substring_index(const char* base,
                                                          const char* sub);
    NTEXTUTILSPUBFUN int NTEXTUTILSCALL n_string_equal(const char* a,
                                                       const char* b);
    // NTEXTUTILSPUBFUN   char* NTEXTUTILSCALL n_char_pickup(const char *base,
    // const char *delim);
    NTEXTUTILSPUBFUN char* NTEXTUTILSCALL n_string_trim_left(char* inout,
                                                             const char* delim);
    NTEXTUTILSPUBFUN char* NTEXTUTILSCALL
    n_string_trim_right(char* inout, const char* delim);
    NTEXTUTILSPUBFUN char* NTEXTUTILSCALL n_string_trim(char* inout,
                                                        const char* delim);
    NTEXTUTILSPUBFUN char* NTEXTUTILSCALL n_string_join(char* output,
                                                        const char* a,
                                                        const char* b,
                                                        const char* delim);
    NTEXTUTILSPUBFUN void NTEXTUTILSCALL n_string_reverse_in_place(char* head);

    // The following two needs to free explicitly
    NTEXTUTILSPUBFUN char* NTEXTUTILSCALL n_file_read_string(char* out,
                                                             const char* base);
    NTEXTUTILSPUBFUN char* NTEXTUTILSCALL
    n_file_read_fix_length_string(char* out, const char* base, size_t length);
    NTEXTUTILSPUBFUN char* NTEXTUTILSCALL
    n_file_binary_read_string(char* out, const char* base, size_t length);
    NTEXTUTILSPUBFUN void NTEXTUTILSCALL
    n_file_write_string(const char* fileName, const char* content);
    NTEXTUTILSPUBFUN void NTEXTUTILSCALL
    n_file_append_string(const char* fileName, const char* content);
    NTEXTUTILSPUBFUN void NTEXTUTILSCALL n_file_write_fix_length_string(
        const char* fileName, const char* content, size_t length);
    NTEXTUTILSPUBFUN void NTEXTUTILSCALL n_file_binary_write_fix_length_string(
        const char* fileName, const char* content, size_t length);
    NTEXTUTILSPUBFUN char* NTEXTUTILSCALL n_string_concat(char* out, int count,
                                                          ...);
    NTEXTUTILSPUBFUN char* NTEXTUTILSCALL n_convert_int_to_string(char* out,
                                                                  int number);

    NTEXTUTILSPUBFUN char* NTEXTUTILSCALL
    n_file_hex_read_string(char* out, const char* f_name, size_t length);

    // NString related functions
    NTEXTUTILSPUBFUN NString NTEXTUTILSCALL n_NString_init(const char* input);
    NTEXTUTILSPUBFUN NStringPtr NTEXTUTILSCALL
    n_NStringPtr_init(const char* input);
    NTEXTUTILSPUBFUN void NTEXTUTILSCALL n_NStringPtr_free(NStringPtr input);
    NTEXTUTILSPUBFUN NString NTEXTUTILSCALL n_NString_join(NString a, NString b,
                                                           const char* delim);
    NTEXTUTILSPUBFUN NString NTEXTUTILSCALL
    n_string_split_first_by_token(const char* a, const char* delim);
    NTEXTUTILSPUBFUN NString NTEXTUTILSCALL
    n_string_split_rest_by_token(const char* a, const char* delim);
    NTEXTUTILSPUBFUN NString NTEXTUTILSCALL
    n_string_split_last_by_token(const char* a, const char* delim);
    NTEXTUTILSPUBFUN NString NTEXTUTILSCALL
    n_string_split_previous_by_token(const char* a, const char* delim);
    NTEXTUTILSPUBFUN NString NTEXTUTILSCALL
    n_string_split_first_by_index(const char* a, const char* delim);
    NTEXTUTILSPUBFUN NString NTEXTUTILSCALL
    n_string_split_rest_by_index(const char* a, const char* delim);
    NTEXTUTILSPUBFUN NString NTEXTUTILSCALL
    n_string_split_last_by_index(const char* a, const char* delim);
    NTEXTUTILSPUBFUN NString NTEXTUTILSCALL
    n_string_split_previous_by_index(const char* a, const char* delim);
    NTEXTUTILSPUBFUN NString NTEXTUTILSCALL n_current_time_as_string();
    NTEXTUTILSPUBFUN time_t NTEXTUTILSCALL n_future_time_as_int(int future);
    NTEXTUTILSPUBFUN NString NTEXTUTILSCALL n_future_time_as_string(int future);

    // NStringArray related functions
    NTEXTUTILSPUBFUN NStringArray NTEXTUTILSCALL
    n_double_to_NStringArray(double* input, int length, const char* format);
    NTEXTUTILSPUBFUN NStringArray NTEXTUTILSCALL
    n_NStringArray_init(int length);
    NTEXTUTILSPUBFUN NStringArrayPtr NTEXTUTILSCALL
    n_NStringArrayPtr_init(int length);
    NTEXTUTILSPUBFUN void NTEXTUTILSCALL
    n_NStringArrayPtr_free(NStringArrayPtr input);
    NTEXTUTILSPUBFUN NString NTEXTUTILSCALL
    n_NStringArray_join(NStringArray a, const char* delim);
    NTEXTUTILSPUBFUN NStringArray NTEXTUTILSCALL
    n_string_split(const char* base, const char* delim);
    NTEXTUTILSPUBFUN int NTEXTUTILSCALL
    n_NStringArray_contain_string(NStringArray a, const char* b);
    NTEXTUTILSPUBFUN int NTEXTUTILSCALL
    n_NStringArray_string_index(NStringArray a, const char* b);

    // NTEXTUTILSPUBFUN   int NTEXTUTILSCALL n_regex_compile(regex_t * r, const
    // char * regex_text); NTEXTUTILSPUBFUN regmatch_t NTEXTUTILSCALL
    // n_regex_match_nth_ngroup(char *matched, regex_t * r, const char *
    // to_match, int nth, int ngroup);

#ifdef __cplusplus
}
#endif

#endif /*__NTEXTUTILS_H__*/