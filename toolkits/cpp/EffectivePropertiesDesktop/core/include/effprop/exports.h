#ifndef __SUANEFFPROPEXPORTS_H__
#define __SUANEFFPROPEXPORTS_H__

#define SUANEFFPROPPUBFUN
#define SUANEFFPROPPUBVAR
#define SUANEFFPROPCALL
#define SUANEFFPROPCDECL

/* Windows platform with MS compiler */
#if defined(_WIN32) && defined(_MSC_VER)
  #undef SUANEFFPROPPUBFUN
  #undef SUANEFFPROPPUBVAR
  #undef SUANEFFPROPCALL
  #undef SUANEFFPROPCDECL
  #if defined(IN_LIBSUANEFFPROP) && !defined(LIBSUANEFFPROP_STATIC)
    #define SUANEFFPROPPUBFUN __declspec(dllexport)
    #define SUANEFFPROPPUBVAR __declspec(dllexport)
  #else
    #define SUANEFFPROPPUBFUN
    #if !defined(LIBSUANEFFPROP_STATIC)
      #define SUANEFFPROPPUBVAR __declspec(dllimport) extern
    #else
      #define SUANEFFPROPPUBVAR extern
    #endif
  #endif
  #if defined(LIBSUANEFFPROP_FASTCALL)
    #define SUANEFFPROPCALL __fastcall
  #else
    #define SUANEFFPROPCALL __cdecl
  #endif
  #define SUANEFFPROPCDECL __cdecl
#endif

/* Windows platform with Borland compiler */
#if defined(_WIN32) && defined(__BORLANDC__)
  #undef SUANEFFPROPPUBFUN
  #undef SUANEFFPROPPUBVAR
  #undef SUANEFFPROPCALL
  #undef SUANEFFPROPCDECL
  #if defined(IN_LIBSUANEFFPROP) && !defined(LIBSUANEFFPROP_STATIC)
    #define SUANEFFPROPPUBFUN __declspec(dllexport)
    #define SUANEFFPROPPUBVAR __declspec(dllexport) extern
  #else
    #define SUANEFFPROPPUBFUN
    #if !defined(LIBSUANEFFPROP_STATIC)
      #define SUANEFFPROPPUBVAR __declspec(dllimport) extern
    #else
      #define SUANEFFPROPPUBVAR extern
    #endif
  #endif
  #define SUANEFFPROPCALL __cdecl
  #define SUANEFFPROPCDECL __cdecl
#endif

/* Windows platform with GNU compiler (Mingw) */
#if defined(_WIN32) && defined(__MINGW32__)
  #undef SUANEFFPROPPUBFUN
  #undef SUANEFFPROPPUBVAR
  #undef SUANEFFPROPCALL
  #undef SUANEFFPROPCDECL
  /*
   * if defined(IN_LIBSUANEFFPROP) this raises problems on mingw with msys
   * _imp__SUANEFFPROPFree listed as missing. Try to workaround the problem
   * by also making that declaration when compiling client code.
   */
  #if defined(IN_LIBSUANEFFPROP) && !defined(LIBSUANEFFPROP_STATIC)
    #define SUANEFFPROPPUBFUN __declspec(dllexport)
    #define SUANEFFPROPPUBVAR __declspec(dllexport) extern
  #else
    #define SUANEFFPROPPUBFUN
    #if !defined(LIBSUANEFFPROP_STATIC)
      #define SUANEFFPROPPUBVAR __declspec(dllimport) extern
    #else
      #define SUANEFFPROPPUBVAR extern
    #endif
  #endif
  #define SUANEFFPROPCALL __cdecl
  #define SUANEFFPROPCDECL __cdecl
#endif

/* Cygwin platform (does not define _WIN32), GNU compiler */
#if defined(__CYGWIN__)
  #undef SUANEFFPROPPUBFUN
  #undef SUANEFFPROPPUBVAR
  #undef SUANEFFPROPCALL
  #undef SUANEFFPROPCDECL
  #if defined(IN_LIBSUANEFFPROP) && !defined(LIBSUANEFFPROP_STATIC)
    #define SUANEFFPROPPUBFUN __declspec(dllexport)
    #define SUANEFFPROPPUBVAR __declspec(dllexport)
  #else
    #define SUANEFFPROPPUBFUN
    #if !defined(LIBSUANEFFPROP_STATIC)
      #define SUANEFFPROPPUBVAR __declspec(dllimport) extern
    #else
      #define SUANEFFPROPPUBVAR extern
    #endif
  #endif
  #define SUANEFFPROPCALL __cdecl
  #define SUANEFFPROPCDECL __cdecl
#endif

/* Compatibility */
#if !defined(LIBSUANEFFPROP_DLL_IMPORT)
#define LIBSUANEFFPROP_DLL_IMPORT SUANEFFPROPPUBVAR
#endif

#endif
