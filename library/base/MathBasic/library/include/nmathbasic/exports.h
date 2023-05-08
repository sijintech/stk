#ifndef __NMATHBASICEXPORTS_H__
#define __NMATHBASICEXPORTS_H__

#define NMATHBASICPUBFUN
#define NMATHBASICPUBVAR
#define NMATHBASICCALL
#define NMATHBASICCDECL

/* Windows platform with MS compiler */
#if defined(_WIN32) && defined(_MSC_VER)
  #undef NMATHBASICPUBFUN
  #undef NMATHBASICPUBVAR
  #undef NMATHBASICCALL
  #undef NMATHBASICCDECL
  #if defined(IN_LIBNMATHBASIC) && !defined(LIBNMATHBASIC_STATIC)
    #define NMATHBASICPUBFUN __declspec(dllexport)
    #define NMATHBASICPUBVAR __declspec(dllexport)
  #else
    #define NMATHBASICPUBFUN
    #if !defined(LIBNMATHBASIC_STATIC)
      #define NMATHBASICPUBVAR __declspec(dllimport) extern
    #else
      #define NMATHBASICPUBVAR extern
    #endif
  #endif
  #if defined(LIBNMATHBASIC_FASTCALL)
    #define NMATHBASICCALL __fastcall
  #else
    #define NMATHBASICCALL __cdecl
  #endif
  #define NMATHBASICCDECL __cdecl
#endif

/* Windows platform with Borland compiler */
#if defined(_WIN32) && defined(__BORLANDC__)
  #undef NMATHBASICPUBFUN
  #undef NMATHBASICPUBVAR
  #undef NMATHBASICCALL
  #undef NMATHBASICCDECL
  #if defined(IN_LIBNMATHBASIC) && !defined(LIBNMATHBASIC_STATIC)
    #define NMATHBASICPUBFUN __declspec(dllexport)
    #define NMATHBASICPUBVAR __declspec(dllexport) extern
  #else
    #define NMATHBASICPUBFUN
    #if !defined(LIBNMATHBASIC_STATIC)
      #define NMATHBASICPUBVAR __declspec(dllimport) extern
    #else
      #define NMATHBASICPUBVAR extern
    #endif
  #endif
  #define NMATHBASICCALL __cdecl
  #define NMATHBASICCDECL __cdecl
#endif

/* Windows platform with GNU compiler (Mingw) */
#if defined(_WIN32) && defined(__MINGW32__)
  #undef NMATHBASICPUBFUN
  #undef NMATHBASICPUBVAR
  #undef NMATHBASICCALL
  #undef NMATHBASICCDECL
  /*
   * if defined(IN_LIBNMATHBASIC) this raises problems on mingw with msys
   * _imp__NMATHBASICFree listed as missing. Try to workaround the problem
   * by also making that declaration when compiling client code.
   */
  #if defined(IN_LIBNMATHBASIC) && !defined(LIBNMATHBASIC_STATIC)
    #define NMATHBASICPUBFUN __declspec(dllexport)
    #define NMATHBASICPUBVAR __declspec(dllexport) extern
  #else
    #define NMATHBASICPUBFUN
    #if !defined(LIBNMATHBASIC_STATIC)
      #define NMATHBASICPUBVAR __declspec(dllimport) extern
    #else
      #define NMATHBASICPUBVAR extern
    #endif
  #endif
  #define NMATHBASICCALL __cdecl
  #define NMATHBASICCDECL __cdecl
#endif

/* Cygwin platform (does not define _WIN32), GNU compiler */
#if defined(__CYGWIN__)
  #undef NMATHBASICPUBFUN
  #undef NMATHBASICPUBVAR
  #undef NMATHBASICCALL
  #undef NMATHBASICCDECL
  #if defined(IN_LIBNMATHBASIC) && !defined(LIBNMATHBASIC_STATIC)
    #define NMATHBASICPUBFUN __declspec(dllexport)
    #define NMATHBASICPUBVAR __declspec(dllexport)
  #else
    #define NMATHBASICPUBFUN
    #if !defined(LIBNMATHBASIC_STATIC)
      #define NMATHBASICPUBVAR __declspec(dllimport) extern
    #else
      #define NMATHBASICPUBVAR extern
    #endif
  #endif
  #define NMATHBASICCALL __cdecl
  #define NMATHBASICCDECL __cdecl
#endif

/* Compatibility */
#if !defined(LIBNMATHBASIC_DLL_IMPORT)
#define LIBNMATHBASIC_DLL_IMPORT NMATHBASICPUBVAR
#endif

#endif
