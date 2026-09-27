#ifndef __NMATERIALGENERATOREXPORTS_H__
#define __NMATERIALGENERATOREXPORTS_H__

#define NMATERIALGENERATORPUBFUN
#define NMATERIALGENERATORPUBVAR
#define NMATERIALGENERATORCALL
#define NMATERIALGENERATORCDECL

/* Windows platform with MS compiler */
#if defined(_WIN32) && defined(_MSC_VER)
#undef NMATERIALGENERATORPUBFUN
#undef NMATERIALGENERATORPUBVAR
#undef NMATERIALGENERATORCALL
#undef NMATERIALGENERATORCDECL
#if defined(IN_LIBNMATERIALGENERATOR) && !defined(LIBNMATERIALGENERATOR_STATIC)
#define NMATERIALGENERATORPUBFUN __declspec(dllexport)
#define NMATERIALGENERATORPUBVAR __declspec(dllexport)
#else
#define NMATERIALGENERATORPUBFUN
#if !defined(LIBNMATERIALGENERATOR_STATIC)
#define NMATERIALGENERATORPUBVAR __declspec(dllimport) extern
#else
#define NMATERIALGENERATORPUBVAR extern
#endif
#endif
#if defined(LIBNMATERIALGENERATOR_FASTCALL)
#define NMATERIALGENERATORCALL __fastcall
#else
#define NMATERIALGENERATORCALL __cdecl
#endif
#define NMATERIALGENERATORCDECL __cdecl
#endif

/* Windows platform with Borland compiler */
#if defined(_WIN32) && defined(__BORLANDC__)
#undef NMATERIALGENERATORPUBFUN
#undef NMATERIALGENERATORPUBVAR
#undef NMATERIALGENERATORCALL
#undef NMATERIALGENERATORCDECL
#if defined(IN_LIBNMATERIALGENERATOR) && !defined(LIBNMATERIALGENERATOR_STATIC)
#define NMATERIALGENERATORPUBFUN __declspec(dllexport)
#define NMATERIALGENERATORPUBVAR __declspec(dllexport) extern
#else
#define NMATERIALGENERATORPUBFUN
#if !defined(LIBNMATERIALGENERATOR_STATIC)
#define NMATERIALGENERATORPUBVAR __declspec(dllimport) extern
#else
#define NMATERIALGENERATORPUBVAR extern
#endif
#endif
#define NMATERIALGENERATORCALL __cdecl
#define NMATERIALGENERATORCDECL __cdecl
#endif

/* Windows platform with GNU compiler (Mingw) */
#if defined(_WIN32) && defined(__MINGW32__)
#undef NMATERIALGENERATORPUBFUN
#undef NMATERIALGENERATORPUBVAR
#undef NMATERIALGENERATORCALL
#undef NMATERIALGENERATORCDECL
/*
 * if defined(IN_LIBNMATERIALGENERATOR) this raises problems on mingw with msys
 * _imp__NMATERIALGENERATOR Free listed as missing. Try to workaround the
 * problem by also making that declaration when compiling client code.
 */
#if defined(IN_LIBNMATERIALGENERATOR) && !defined(LIBNMATERIALGENERATOR_STATIC)
#define NMATERIALGENERATORPUBFUN __declspec(dllexport)
#define NMATERIALGENERATORPUBVAR __declspec(dllexport) extern
#else
#define NMATERIALGENERATORPUBFUN
#if !defined(LIBNMATERIALGENERATOR_STATIC)
#define NMATERIALGENERATORPUBVAR __declspec(dllimport) extern
#else
#define NMATERIALGENERATORPUBVAR extern
#endif
#endif
#define NMATERIALGENERATORCALL __cdecl
#define NMATERIALGENERATORCDECL __cdecl
#endif

/* Cygwin platform (does not define _WIN32), GNU compiler */
#if defined(__CYGWIN__)
#undef NMATERIALGENERATORPUBFUN
#undef NMATERIALGENERATORPUBVAR
#undef NMATERIALGENERATORCALL
#undef NMATERIALGENERATORCDECL
#if defined(IN_LIBNMATERIALGENERATOR) && !defined(LIBNMATERIALGENERATOR_STATIC)
#define NMATERIALGENERATORPUBFUN __declspec(dllexport)
#define NMATERIALGENERATORPUBVAR __declspec(dllexport)
#else
#define NMATERIALGENERATORPUBFUN
#if !defined(LIBNMATERIALGENERATOR_STATIC)
#define NMATERIALGENERATORPUBVAR __declspec(dllimport) extern
#else
#define NMATERIALGENERATORPUBVAR extern
#endif
#endif
#define NMATERIALGENERATORCALL __cdecl
#define NMATERIALGENERATORCDECL __cdecl
#endif

/* Compatibility */
#if !defined(LIBNMATERIALGENERATOR_DLL_IMPORT)
#define LIBNMATERIALGENERATOR_DLL_IMPORT NMATERIALGENERATORPUBVAR
#endif

#endif
