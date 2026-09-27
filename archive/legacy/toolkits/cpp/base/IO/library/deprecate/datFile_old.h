/**
 * Class:
 * Description:
 * Parameters:
 * Methods:
 */

#ifndef __DATFILE_H__
#define __DATFILE_H__

#include <libxml/parser.h>
#include <libxml/xpath.h>
#include <niobasic/exports.h>
#include <niobasic/errors.h>
#include <stdlib.h>
#include <stdio.h>
#include <unistd.h>
#include <ntextutils/ntextutils.h>
#include "unity.h"
#include "zf_log.h"
#ifdef __cplusplus
extern "C"{
#endif

// Double precision
typedef struct {
    int dim1,dim2,dim3,component;
    double *data;
} Dat_4D_double;
typedef Dat_4D_double* DatPtr_4D_double;

NIOBASICPUBFUN DatPtr_4D_double NIOBASICCALL Dat_4D_double_init( int x, int y, int z, int component);
NIOBASICPUBFUN void NIOBASICCALL Dat_4D_double_free(DatPtr_4D_double data);
NIOBASICPUBFUN double NIOBASICCALL Dat_4D_double_get(const DatPtr_4D_double data, const int i, const int j, const int k, const int l);
NIOBASICPUBFUN void NIOBASICCALL Dat_4D_double_set(DatPtr_4D_double data, const int i, const int j, const int k, const int l, double x);
NIOBASICPUBFUN void NIOBASICCALL datFile_4D_double_read(DatPtr_4D_double data, const char *file);
NIOBASICPUBFUN void NIOBASICCALL datFile_4D_double_write(DatPtr_4D_double data, const char *file);

// Integer
typedef struct {
    int dim1,dim2,dim3,component;
    int *data;
} Dat_4D_int;
typedef Dat_4D_int* DatPtr_4D_int;

NIOBASICPUBFUN DatPtr_4D_int NIOBASICCALL Dat_4D_int_init( int x, int y, int z, int component);
NIOBASICPUBFUN void NIOBASICCALL Dat_4D_int_free(DatPtr_4D_int data);
NIOBASICPUBFUN int NIOBASICCALL Dat_4D_int_get(const DatPtr_4D_int data, const int i, const int j, const int k, const int l);
NIOBASICPUBFUN void NIOBASICCALL Dat_4D_int_set(DatPtr_4D_int data, const int i, const int j, const int k, const int l, int x);
NIOBASICPUBFUN void NIOBASICCALL datFile_4D_int_read(DatPtr_4D_int data, const char *file);
NIOBASICPUBFUN void NIOBASICCALL datFile_4D_int_write(DatPtr_4D_int data, const char *file);
#ifdef __cplusplus
}
#endif


#endif /*__DATFILE_H__*/
