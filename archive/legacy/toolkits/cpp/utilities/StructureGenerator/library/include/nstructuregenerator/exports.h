#ifndef __NSTRUCTUREGENERATOREXPORTS_H__
#define __NSTRUCTUREGENERATOREXPORTS_H__

#define NSTRUCTUREGENERATORPUBFUN
#define NSTRUCTUREGENERATORPUBVAR
#define NSTRUCTUREGENERATORCALL
#define NSTRUCTUREGENERATORCDECL

/* Windows platform with MS compiler */
#if defined(_WIN32) && defined(_MSC_VER)
  #undef NSTRUCTUREGENERATORPUBFUN
  #undef NSTRUCTUREGENERATORPUBVAR
  #undef NSTRUCTUREGENERATORCALL
  #undef NSTRUCTUREGENERATORCDECL
  #if defined(IN_LIBNSTRUCTUREGENERATOR) && !defined(LIBNSTRUCTUREGENERATOR_STATIC)
    #define NSTRUCTUREGENERATORPUBFUN __declspec(dllexport)
    #define NSTRUCTUREGENERATORPUBVAR __declspec(dllexport)
  #else
    #define NSTRUCTUREGENERATORPUBFUN
    #if !defined(LIBNSTRUCTUREGENERATOR_STATIC)
      #define NSTRUCTUREGENERATORPUBVAR __declspec(dllimport) extern
    #else
      #define NSTRUCTUREGENERATORPUBVAR extern
    #endif
  #endif
  #if defined(LIBNSTRUCTUREGENERATOR_FASTCALL)
    #define NSTRUCTUREGENERATORCALL __fastcall
  #else
    #define NSTRUCTUREGENERATORCALL __cdecl
  #endif
  #define NSTRUCTUREGENERATORCDECL __cdecl
#endif

/* Windows platform with Borland compiler */
#if defined(_WIN32) && defined(__BORLANDC__)
  #undef NSTRUCTUREGENERATORPUBFUN
  #undef NSTRUCTUREGENERATORPUBVAR
  #undef NSTRUCTUREGENERATORCALL
  #undef NSTRUCTUREGENERATORCDECL
  #if defined(IN_LIBNSTRUCTUREGENERATOR) && !defined(LIBNSTRUCTUREGENERATOR_STATIC)
    #define NSTRUCTUREGENERATORPUBFUN __declspec(dllexport)
    #define NSTRUCTUREGENERATORPUBVAR __declspec(dllexport) extern
  #else
    #define NSTRUCTUREGENERATORPUBFUN
    #if !defined(LIBNSTRUCTUREGENERATOR_STATIC)
      #define NSTRUCTUREGENERATORPUBVAR __declspec(dllimport) extern
    #else
      #define NSTRUCTUREGENERATORPUBVAR extern
    #endif
  #endif
  #define NSTRUCTUREGENERATORCALL __cdecl
  #define NSTRUCTUREGENERATORCDECL __cdecl
#endif

/* Windows platform with GNU compiler (Mingw) */
#if defined(_WIN32) && defined(__MINGW32__)
  #undef NSTRUCTUREGENERATORPUBFUN
  #undef NSTRUCTUREGENERATORPUBVAR
  #undef NSTRUCTUREGENERATORCALL
  #undef NSTRUCTUREGENERATORCDECL
  /*
   * if defined(IN_LIBNSTRUCTUREGENERATOR) this raises problems on mingw with msys
   * _imp__NSTRUCTUREGENERATOR Free listed as missing. Try to workaround the problem
   * by also making that declaration when compiling client code.
   */
  #if defined(IN_LIBNSTRUCTUREGENERATOR) && !defined(LIBNSTRUCTUREGENERATOR_STATIC)
    #define NSTRUCTUREGENERATORPUBFUN __declspec(dllexport)
    #define NSTRUCTUREGENERATORPUBVAR __declspec(dllexport) extern
  #else
    #define NSTRUCTUREGENERATORPUBFUN
    #if !defined(LIBNSTRUCTUREGENERATOR_STATIC)
      #define NSTRUCTUREGENERATORPUBVAR __declspec(dllimport) extern
    #else
      #define NSTRUCTUREGENERATORPUBVAR extern
    #endif
  #endif
  #define NSTRUCTUREGENERATORCALL __cdecl
  #define NSTRUCTUREGENERATORCDECL __cdecl
#endif

/* Cygwin platform (does not define _WIN32), GNU compiler */
#if defined(__CYGWIN__)
  #undef NSTRUCTUREGENERATORPUBFUN
  #undef NSTRUCTUREGENERATORPUBVAR
  #undef NSTRUCTUREGENERATORCALL
  #undef NSTRUCTUREGENERATORCDECL
  #if defined(IN_LIBNSTRUCTUREGENERATOR) && !defined(LIBNSTRUCTUREGENERATOR_STATIC)
    #define NSTRUCTUREGENERATORPUBFUN __declspec(dllexport)
    #define NSTRUCTUREGENERATORPUBVAR __declspec(dllexport)
  #else
    #define NSTRUCTUREGENERATORPUBFUN
    #if !defined(LIBNSTRUCTUREGENERATOR_STATIC)
      #define NSTRUCTUREGENERATORPUBVAR __declspec(dllimport) extern
    #else
      #define NSTRUCTUREGENERATORPUBVAR extern
    #endif
  #endif
  #define NSTRUCTUREGENERATORCALL __cdecl
  #define NSTRUCTUREGENERATORCDECL __cdecl
#endif

/* Compatibility */
#if !defined(LIBNSTRUCTUREGENERATOR_DLL_IMPORT)
#define LIBNSTRUCTUREGENERATOR_DLL_IMPORT NSTRUCTUREGENERATORPUBVAR
#endif

#endif
