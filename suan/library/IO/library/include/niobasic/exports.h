#ifndef __NIOBASICEXPORTS_H__
#define __NIOBASICEXPORTS_H__

#define NIOBASICPUBFUN
#define NIOBASICPUBVAR
#define NIOBASICCALL
#define NIOBASICCDECL

/* Windows platform with MS compiler */
#if defined(_WIN32) && defined(_MSC_VER)
  #undef NIOBASICPUBFUN
  #undef NIOBASICPUBVAR
  #undef NIOBASICCALL
  #undef NIOBASICCDECL
  #if defined(IN_LIBNIOBASIC) && !defined(LIBNIOBASIC_STATIC)
    #define NIOBASICPUBFUN __declspec(dllexport)
    #define NIOBASICPUBVAR __declspec(dllexport)
  #else
    #define NIOBASICPUBFUN
    #if !defined(LIBNIOBASIC_STATIC)
      #define NIOBASICPUBVAR __declspec(dllimport) extern
    #else
      #define NIOBASICPUBVAR extern
    #endif
  #endif
  #if defined(LIBNIOBASIC_FASTCALL)
    #define NIOBASICCALL __fastcall
  #else
    #define NIOBASICCALL __cdecl
  #endif
  #define NIOBASICCDECL __cdecl
#endif

/* Windows platform with Borland compiler */
#if defined(_WIN32) && defined(__BORLANDC__)
  #undef NIOBASICPUBFUN
  #undef NIOBASICPUBVAR
  #undef NIOBASICCALL
  #undef NIOBASICCDECL
  #if defined(IN_LIBNIOBASIC) && !defined(LIBNIOBASIC_STATIC)
    #define NIOBASICPUBFUN __declspec(dllexport)
    #define NIOBASICPUBVAR __declspec(dllexport) extern
  #else
    #define NIOBASICPUBFUN
    #if !defined(LIBNIOBASIC_STATIC)
      #define NIOBASICPUBVAR __declspec(dllimport) extern
    #else
      #define NIOBASICPUBVAR extern
    #endif
  #endif
  #define NIOBASICCALL __cdecl
  #define NIOBASICCDECL __cdecl
#endif

/* Windows platform with GNU compiler (Mingw) */
#if defined(_WIN32) && defined(__MINGW32__)
  #undef NIOBASICPUBFUN
  #undef NIOBASICPUBVAR
  #undef NIOBASICCALL
  #undef NIOBASICCDECL
  /*
   * if defined(IN_LIBNIOBASIC) this raises problems on mingw with msys
   * _imp__NIOBASICFree listed as missing. Try to workaround the problem
   * by also making that declaration when compiling client code.
   */
  #if defined(IN_LIBNIOBASIC) && !defined(LIBNIOBASIC_STATIC)
    #define NIOBASICPUBFUN __declspec(dllexport)
    #define NIOBASICPUBVAR __declspec(dllexport) extern
  #else
    #define NIOBASICPUBFUN
    #if !defined(LIBNIOBASIC_STATIC)
      #define NIOBASICPUBVAR __declspec(dllimport) extern
    #else
      #define NIOBASICPUBVAR extern
    #endif
  #endif
  #define NIOBASICCALL __cdecl
  #define NIOBASICCDECL __cdecl
#endif

/* Cygwin platform (does not define _WIN32), GNU compiler */
#if defined(__CYGWIN__)
  #undef NIOBASICPUBFUN
  #undef NIOBASICPUBVAR
  #undef NIOBASICCALL
  #undef NIOBASICCDECL
  #if defined(IN_LIBNIOBASIC) && !defined(LIBNIOBASIC_STATIC)
    #define NIOBASICPUBFUN __declspec(dllexport)
    #define NIOBASICPUBVAR __declspec(dllexport)
  #else
    #define NIOBASICPUBFUN
    #if !defined(LIBNIOBASIC_STATIC)
      #define NIOBASICPUBVAR __declspec(dllimport) extern
    #else
      #define NIOBASICPUBVAR extern
    #endif
  #endif
  #define NIOBASICCALL __cdecl
  #define NIOBASICCDECL __cdecl
#endif

/* Compatibility */
#if !defined(LIBNIOBASIC_DLL_IMPORT)
#define LIBNIOBASIC_DLL_IMPORT NIOBASICPUBVAR
#endif

#endif
