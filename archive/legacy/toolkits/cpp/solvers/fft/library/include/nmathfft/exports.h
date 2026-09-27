#ifndef __NMATHFFTEXPORTS_H__
#define __NMATHFFTEXPORTS_H__

#define NMATHFFTPUBFUN
#define NMATHFFTPUBVAR
#define NMATHFFTCALL
#define NMATHFFTCDECL

/* Windows platform with MS compiler */
#if defined(_WIN32) && defined(_MSC_VER)
#undef NMATHFFTPUBFUN
#undef NMATHFFTPUBVAR
#undef NMATHFFTCALL
#undef NMATHFFTCDECL
#if defined(IN_LIBNMATHFFT) && !defined(LIBNMATHFFT_STATIC)
#define NMATHFFTPUBFUN __declspec(dllexport)
#define NMATHFFTPUBVAR __declspec(dllexport)
#else
#define NMATHFFTPUBFUN
#if !defined(LIBNMATHFFT_STATIC)
#define NMATHFFTPUBVAR __declspec(dllimport) extern
#else
#define NMATHFFTPUBVAR extern
#endif
#endif
#if defined(LIBNMATHFFT_FASTCALL)
#define NMATHFFTCALL __fastcall
#else
#define NMATHFFTCALL __cdecl
#endif
#define NMATHFFTCDECL __cdecl
#endif

/* Windows platform with Borland compiler */
#if defined(_WIN32) && defined(__BORLANDC__)
#undef NMATHFFTPUBFUN
#undef NMATHFFTPUBVAR
#undef NMATHFFTCALL
#undef NMATHFFTCDECL
#if defined(IN_LIBNMATHFFT) && !defined(LIBNMATHFFT_STATIC)
#define NMATHFFTPUBFUN __declspec(dllexport)
#define NMATHFFTPUBVAR __declspec(dllexport) extern
#else
#define NMATHFFTPUBFUN
#if !defined(LIBNMATHFFT_STATIC)
#define NMATHFFTPUBVAR __declspec(dllimport) extern
#else
#define NMATHFFTPUBVAR extern
#endif
#endif
#define NMATHFFTCALL __cdecl
#define NMATHFFTCDECL __cdecl
#endif

/* Windows platform with GNU compiler (Mingw) */
#if defined(_WIN32) && defined(__MINGW32__)
#undef NMATHFFTPUBFUN
#undef NMATHFFTPUBVAR
#undef NMATHFFTCALL
#undef NMATHFFTCDECL
/*
   * if defined(IN_LIBNMATHFFT) this raises problems on mingw with msys
   * _imp__NMATHFFTFree listed as missing. Try to workaround the problem
   * by also making that declaration when compiling client code.
   */
#if defined(IN_LIBNMATHFFT) && !defined(LIBNMATHFFT_STATIC)
#define NMATHFFTPUBFUN __declspec(dllexport)
#define NMATHFFTPUBVAR __declspec(dllexport) extern
#else
#define NMATHFFTPUBFUN
#if !defined(LIBNMATHFFT_STATIC)
#define NMATHFFTPUBVAR __declspec(dllimport) extern
#else
#define NMATHFFTPUBVAR extern
#endif
#endif
#define NMATHFFTCALL __cdecl
#define NMATHFFTCDECL __cdecl
#endif

/* Cygwin platform (does not define _WIN32), GNU compiler */
#if defined(__CYGWIN__)
#undef NMATHFFTPUBFUN
#undef NMATHFFTPUBVAR
#undef NMATHFFTCALL
#undef NMATHFFTCDECL
#if defined(IN_LIBNMATHFFT) && !defined(LIBNMATHFFT_STATIC)
#define NMATHFFTPUBFUN __declspec(dllexport)
#define NMATHFFTPUBVAR __declspec(dllexport)
#else
#define NMATHFFTPUBFUN
#if !defined(LIBNMATHFFT_STATIC)
#define NMATHFFTPUBVAR __declspec(dllimport) extern
#else
#define NMATHFFTPUBVAR extern
#endif
#endif
#define NMATHFFTCALL __cdecl
#define NMATHFFTCDECL __cdecl
#endif

/* Compatibility */
#if !defined(LIBNMATHFFT_DLL_IMPORT)
#define LIBNMATHFFT_DLL_IMPORT NMATHFFTPUBVAR
#endif

#endif
