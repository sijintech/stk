#ifndef __DATFILE_H__
#define __DATFILE_H__

//#define _CRT_SECURE_NO_WARNINGS
#define _CRT_NONSTDC_NO_DEPRECATE

#include <libxml/xmlwriter.h>
#include "zf_log.h"
// #include "nmathbasic/nmathbasic.h"
#include "niobasic/exports.h"
#include "niobasic/controlFile.h"
#include <nmathbasic/nmathbasic.h>

#define MY_DAT_ENCODING "UTF-8"
#define MY_DAT_FORMAT_SCIENTIFIC "%+13.6le "
#define MY_DAT_FORMAT_INT "%+5i "
#define MY_DAT_FORMAT_short "%+d "
#define MY_DAT_CORD_FORMAT "%5i %5i %5i "
#define MY_DAT_HEAD_FORMAT "%5i %5i %5i %5i \n"
#define MY_DAT_ORMAT_LENGTH 14

#ifdef __cplusplus
extern "C"
{
#endif

    NIOBASICPUBFUN void NIOBASICCALL n_datFile_4D_int_read(int x, int y, int z, int c, int data[x][y][z][c], const char *file);
    NIOBASICPUBFUN void NIOBASICCALL n_datFile_3D_int_read(int x, int y, int z, int data[x][y][z], const char *file);
    NIOBASICPUBFUN void NIOBASICCALL n_datFile_4D_int_write(int x, int y, int z, int c, int data[x][y][z][c], const char *file);
    NIOBASICPUBFUN void NIOBASICCALL n_datFile_3D_int_write(int x, int y, int z, int data[x][y][z], const char *file);

    NIOBASICPUBFUN void NIOBASICCALL n_datFile_4D_double_read(int x, int y, int z, int c, double data[x][y][z][c], const char *file);
    NIOBASICPUBFUN void NIOBASICCALL n_datFile_3D_double_read(int x, int y, int z, double data[x][y][z], const char *file);
    NIOBASICPUBFUN void NIOBASICCALL n_datFile_4D_double_write(int x, int y, int z, int c, double data[x][y][z][c], const char *file);
    NIOBASICPUBFUN void NIOBASICCALL n_datFile_3D_double_write(int x, int y, int z, double data[x][y][z], const char *file);

    NIOBASICPUBFUN void NIOBASICCALL n_datFile_4D_short_read(int x, int y, int z, int c, short data[x][y][z][c], const char *file);
    NIOBASICPUBFUN void NIOBASICCALL n_datFile_3D_short_read(int x, int y, int z, short data[x][y][z], const char *file);
    NIOBASICPUBFUN void NIOBASICCALL n_datFile_4D_short_write(int x, int y, int z, int c, short data[x][y][z][c], const char *file);
    NIOBASICPUBFUN void NIOBASICCALL n_datFile_3D_short_write(int x, int y, int z, short data[x][y][z], const char *file);

#define n_datFile_4D_read(x, y, z, c, data, file) \
    _Generic((data),                              \
             double *                             \
             : n_datFile_4D_double_read,          \
               int *                              \
             : n_datFile_4D_int_read,             \
               short *                   \
             : n_datFile_4D_short_read)(x, y, z, c, data, file)

#define n_datFile_3D_read(x, y, z, data, file) \
    _Generic((data),                           \
             double *                          \
             : n_datFile_3D_double_read,       \
               int *                           \
             : n_datFile_3D_int_read,          \
               short *                \
             : n_datFile_3D_short_read)(x, y, z, data, file)

#define n_datFile_4D_write(x, y, z, c, data, file) \
    _Generic((data),                              \
             double *                             \
             : n_datFile_4D_double_write,          \
               int *                              \
             : n_datFile_4D_int_write,             \
               short *                   \
             : n_datFile_4D_short_write)(x, y, z, c, data, file)

#define n_datFile_3D_write(x, y, z, data, file) \
    _Generic((data),                           \
             double *                          \
             : n_datFile_3D_double_write,       \
               int *                           \
             : n_datFile_3D_int_write,          \
               short *                \
             : n_datFile_3D_short_write)(x, y, z, data, file)

#define DAT_GET_MACRO(_5,_6,NAME,...) NAME
#define n_datFile_read(...) DAT_GET_MACRO(__VA_ARGS__, n_datFile_3D_read, n_datFile_4D_read)(__VA_ARGS__)
#define n_datFile_write(...) DAT_GET_MACRO(__VA_ARGS__, n_datFile_3D_write, n_datFile_4D_write)(__VA_ARGS__)

#ifdef __cplusplus
}
#endif

#endif