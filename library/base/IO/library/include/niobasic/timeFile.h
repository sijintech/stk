/**
 * Class:
 * Description:
 * Parameters:
 * Methods:
 */

#ifndef __TIMEFILE_H__
#define __TIMEFILE_H__
//#define _CRT_SECURE_NO_WARNINGS
#define _CRT_NONSTDC_NO_DEPRECATE

#include <libxml/parser.h>
#include <libxml/xpath.h>
#include <niobasic/exports.h>
#include <niobasic/errors.h>
#include <stdlib.h>
#include <stdio.h>
//#include <unistd.h>
#include <ntextutils/ntextutils.h>
#include "zf_log.h"
#ifdef __cplusplus
extern "C"{
#endif

// Double precision
#define SEPARATOR ","
NIOBASICPUBFUN void NIOBASICCALL n_timeFile_write_line_from_NStringArray(NStringArray header, const char *file);
NIOBASICPUBFUN void NIOBASICCALL n_timeFile_write_line_from_double(double *input, int length, const char *file);
NIOBASICPUBFUN void NIOBASICCALL n_timeFile_write_line_from_double_f(double **input, int *length, const char *file);
NIOBASICPUBFUN double * NIOBASICCALL n_timeFile_read(double *output, const char *headerName, const char *file);

NIOBASICPUBFUN void NIOBASICCALL n_timeFile_write_line_from_string(const char *input, const char *file);
NIOBASICPUBFUN void NIOBASICCALL n_timeFile_write_line_from_string_f(const char *input, const char *file);
NIOBASICPUBFUN void NIOBASICCALL n_timeFile_write_header_line(const char *input, const char *file);
NIOBASICPUBFUN void NIOBASICCALL n_timeFile_write_header_line_f(const char *input, const char *file);

#ifdef __cplusplus
}
#endif


#endif /*__TIMEFILE_H__*/
