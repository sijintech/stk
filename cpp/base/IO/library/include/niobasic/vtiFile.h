#ifndef __VTIFILE_H__
#define __VTIFILE_H__

//#define _CRT_SECURE_NO_WARNINGS
#define _CRT_NONSTDC_NO_DEPRECATE

#include <libxml/xmlwriter.h>
#include "zf_log.h"
// #include "nmathbasic/nmathbasic.h"
#include "niobasic/exports.h"
#include "niobasic/controlFile.h"
#include <nmathbasic/nmathbasic.h>

#define MY_VTI_ENCODING "UTF-8"
#define MY_VTI_FORMAT_SCIENTIFIC "%+13.6le "
#define MY_VTI_FORMAT_INT "%+i "
#define MY_VTI_FORMAT_short "%+d "
#define MY_VTI_FORMAT_LENGTH 14

#ifdef __cplusplus
extern "C"{
#endif

NIOBASICPUBFUN void NIOBASICCALL n_vtiFile_4D_double_read(int x, int y, int z, int c, double data[x][y][z][c],const char *file);
NIOBASICPUBFUN void NIOBASICCALL n_vtiFile_4D_double_read_f(int *x, int *y, int *z, int *c, double **data, const char *file);
NIOBASICPUBFUN void NIOBASICCALL n_vtiFile_4D_double_write( int x, int y, int z, int c, double data[x][y][z][c],const char *file);
NIOBASICPUBFUN void NIOBASICCALL n_vtiFile_4D_double_write_f( int *x, int *y, int *z, int *c, double **data, const char *fileName);

NIOBASICPUBFUN void NIOBASICCALL n_vtiFile_3D_double_read(int x, int y, int z, double data[x][y][z],const char *file);
NIOBASICPUBFUN void NIOBASICCALL n_vtiFile_3D_double_read_f(int *x, int *y, int *z, double **data, const char *file);
NIOBASICPUBFUN void NIOBASICCALL n_vtiFile_3D_double_write( int x, int y, int z, double data[x][y][z],const char *file);
NIOBASICPUBFUN void NIOBASICCALL n_vtiFile_3D_double_write_f( int *x, int *y, int *z, double **data, const char *fileName);

NIOBASICPUBFUN void NIOBASICCALL n_vtiFile_4D_int_read(int x, int y, int z, int c, int data[x][y][z][c],const char *file);
NIOBASICPUBFUN void NIOBASICCALL n_vtiFile_4D_int_read_f(int *x, int *y, int *z, int *c, int **data, const char *file);
NIOBASICPUBFUN void NIOBASICCALL n_vtiFile_4D_int_write(int x, int y, int z, int c, int data[x][y][z][c],const char *file);
NIOBASICPUBFUN void NIOBASICCALL n_vtiFile_4D_int_write_f( int *x, int *y, int *z, int *c, int **data, const char *fileName);

NIOBASICPUBFUN void NIOBASICCALL n_vtiFile_3D_int_read(int x, int y, int z, int data[x][y][z],const char *file);
NIOBASICPUBFUN void NIOBASICCALL n_vtiFile_3D_int_read_f(int *x, int *y, int *z, int **data, const char *file);
NIOBASICPUBFUN void NIOBASICCALL n_vtiFile_3D_int_write(int x, int y, int z, int data[x][y][z],const char *file);
NIOBASICPUBFUN void NIOBASICCALL n_vtiFile_3D_int_write_f( int *x, int *y, int *z,int **data, const char *fileName);

NIOBASICPUBFUN void NIOBASICCALL n_vtiFile_4D_short_read(int x, int y, int z, int c, short data[x][y][z][c],const char *file);
NIOBASICPUBFUN void NIOBASICCALL n_vtiFile_4D_short_read_f(int *x, int *y, int *z, int *c, short **data, const char *file);
NIOBASICPUBFUN void NIOBASICCALL n_vtiFile_4D_short_write(int x, int y, int z, int c, short data[x][y][z][c],const char *file);
NIOBASICPUBFUN void NIOBASICCALL n_vtiFile_4D_short_write_f( int *x, int *y, int *z, int *c, short **data, const char *fileName);

NIOBASICPUBFUN void NIOBASICCALL n_vtiFile_3D_short_read(int x, int y, int z, short data[x][y][z],const char *file);
NIOBASICPUBFUN void NIOBASICCALL n_vtiFile_3D_short_read_f(int *x, int *y, int *z, short **data, const char *file);
NIOBASICPUBFUN void NIOBASICCALL n_vtiFile_3D_short_write(int x, int y, int z, short data[x][y][z],const char *file);
NIOBASICPUBFUN void NIOBASICCALL n_vtiFile_3D_short_write_f( int *x, int *y, int *z,short **data, const char *fileName);

#define n_vtiFile_4D_read(x, y, z, c, data, file) \
    _Generic((data),                              \
             double *                             \
             : n_vtiFile_4D_double_read,          \
               int *                              \
             : n_vtiFile_4D_int_read,             \
               short *                   \
             : n_vtiFile_4D_short_read)(x, y, z, c, data, file)

#define n_vtiFile_3D_read(x, y, z, data, file) \
    _Generic((data),                           \
             double *                          \
             : n_vtiFile_3D_double_read,       \
               int *                           \
             : n_vtiFile_3D_int_read,          \
               short *                \
             : n_vtiFile_3D_short_read)(x, y, z, data, file)

#define n_vtiFile_4D_write(x, y, z, c, data, file) \
    _Generic((data),                              \
             double *                             \
             : n_vtiFile_4D_double_write,          \
               int *                              \
             : n_vtiFile_4D_int_write,             \
               short *                   \
             : n_vtiFile_4D_short_write)(x, y, z, c, data, file)

#define n_vtiFile_3D_write(x, y, z, data, file) \
    _Generic((data),                           \
             double *                          \
             : n_vtiFile_3D_double_write,       \
               int *                           \
             : n_vtiFile_3D_int_write,          \
               short *                \
             : n_vtiFile_3D_short_write)(x, y, z, data, file)

#define VTI_GET_MACRO(_5,_6,NAME,...) NAME
#define n_vtiFile_read(...) VTI_GET_MACRO(__VA_ARGS__, n_vtiFile_3D_read, n_vtiFile_4D_read)(__VA_ARGS__)
#define n_vtiFile_write(...) VTI_GET_MACRO(__VA_ARGS__, n_vtiFile_3D_write, n_vtiFile_4D_write)(__VA_ARGS__)



#ifdef __cplusplus
}
#endif

#endif