#ifndef __DREAM3DFILE_H__
#define __DREAM3DFILE_H__

//#define _CRT_SECURE_NO_WARNINGS
#define _CRT_NONSTDC_NO_DEPRECATE

#include "zf_log.h"
#include <libxml/xmlwriter.h>
// #include "nmathbasic/nmathbasic.h"
#include "niobasic/controlFile.h"
#include "niobasic/exports.h"
#include <nmathbasic/nmathbasic.h>

#ifdef __cplusplus
extern "C" {
#endif

NIOBASICPUBFUN void NIOBASICCALL n_dream3DFile_3D_short_read(
    int x, int y, int z, short data[x][y][z], const char* file);

#define n_dream3DFile_3D_read(x, y, z, data, file)                             \
    _Generic((data), short* : n_dream3DFile_3D_short_read)(x, y, z, data, file)

#define DAT_GET_MACRO(_5, NAME, ...) NAME
#define n_dream3DFile_read(...)                                                \
    DAT_GET_MACRO(__VA_ARGS__, n_dream3DFile_3D_read)                          \
    (__VA_ARGS__)

#ifdef __cplusplus
}
#endif

#endif