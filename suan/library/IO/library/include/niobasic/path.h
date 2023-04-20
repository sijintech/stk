#ifndef __PATHFILE_H__
#define __PATHFILE_H__

//#define _CRT_SECURE_NO_WARNINGS
#define _CRT_NONSTDC_NO_DEPRECATE

#include "zf_log.h"
#include <libxml/xmlwriter.h>
// #include "nmathbasic/nmathbasic.h"
#include "niobasic/exports.h"

#ifdef WIN32
#include <shlwapi.h>
#include <windows.h>
#else
#include <libgen.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#define MAX_PATH 1024
#ifdef __APPLE__
#include <mach-o/dyld.h>
#endif
#endif
#ifdef __cplusplus
extern "C"
{
#endif

    NIOBASICPUBFUN void NIOBASICCALL n_path_get_cwd(char* out);
    NIOBASICPUBFUN void NIOBASICCALL n_path_get_exe_path(char* out);
    NIOBASICPUBFUN void NIOBASICCALL n_path_get_exe_folder(char* out);
    NIOBASICPUBFUN void NIOBASICCALL n_path_concat(char* path, char* extension);
#ifdef __cplusplus
}
#endif

#endif