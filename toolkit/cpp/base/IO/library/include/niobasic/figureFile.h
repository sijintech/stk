/**
 * Class:
 * Description:
 * Parameters:
 * Methods:
 */

#ifndef __FIGUREFILE_H__
#define __FIGUREFILE_H__

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

#define BYTES_PER_PIXEL 3 /// red, green, & blue
#define FILE_HEADER_SIZE 14
#define INFO_HEADER_SIZE 40

// Double precision
NIOBASICPUBFUN void NIOBASICCALL generateBMP(char* imageFileName, int ncolor, double *colormap , int width, int height, double *image  );
NIOBASICPUBFUN void NIOBASICCALL convert_array_double_to_BGR(int ncolor, double *colormap, int width, int height, double *image,  int *color);
NIOBASICPUBFUN void NIOBASICCALL convert_double_to_BGR(int ncolor, double *colormap, double input, int *output);
NIOBASICPUBFUN void NIOBASICCALL convert_array_int_to_uchar(int *image_int, unsigned char *image_uchar, int total_size);

NIOBASICPUBFUN void NIOBASICCALL generateBitmapImage(unsigned char* image, int height, int width, char* imageFileName);
NIOBASICPUBFUN unsigned char* NIOBASICCALL createBitmapFileHeader(int height, int stride);
NIOBASICPUBFUN unsigned char* NIOBASICCALL createBitmapInfoHeader(int height, int width);


#ifdef __cplusplus
}
#endif


#endif /*__TIMEFILE_H__*/
