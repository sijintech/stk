

//#define _CRT_SECURE_NO_WARNINGS
#define _CRT_NONSTDC_NO_DEPRECATE

#ifndef __NMATHBASIC_H__
#define __NMATHBASIC_H__

#define NMATHBASIC_VERSION_MAJOR 0
#define NMATHBASIC_VERSION_MINOR 1
#define NMATHBASIC_VERSION_PATCH 1
#define NMATHBASIC_VERSION ((NMATHBASIC_VERSION_MAJOR << 16) | (NMATHBASIC_VERSION_MINOR << 8) | NMATHBASIC_VERSION_PATCH)

// Include from std C library
#include <stdio.h>
#include "stdlib.h"
//#include <unistd.h>
#include <math.h>
#include <zf_log.h>
#include <time.h>
// Include of library developed by Nibiru
#include <nmathbasic/exports.h>
#include <nmathbasic/errors.h>
#include <nmathbasic/array.h>
#include <nmathbasic/matrix.h>
#include <nmathbasic/vector.h>
#include <nmathbasic/tensor.h>
#include <nmathbasic/transformation.h>
#include <nmathbasic/random.h>
// #include <nmathbasic/lapack.h>
#include <nmathbasic/decompose.h>

#define foreach(a, b, c) for (int a = b; a < c; a++)
#define for_i foreach (i, 0, n)
#define for_j foreach (j, 0, n)
#define for_k foreach (k, 0, n)
#define for_ij for_i for_j
#define for_ijk for_ij for_k
#define swap(x, y)     \
  {                    \
    typeof(x) tmp = x; \
    x = y;             \
    y = tmp;           \
  }
#define sum_k(a, b, c, s) \
  {                       \
    s = 0;                \
    foreach (k, a, b)     \
      s += c;             \
  }
#define NPTR2ARR1D(T,ptr,x) (*(T(*)[x])ptr)
#define NPTR2ARR2D(T,ptr,x,y) (*(T(*)[x][y])ptr)
#define NPTR2ARR3D(T,ptr,x,y,z) (*(T(*)[x][y][z])ptr)
#define NPTR2ARR4D(T,ptr,x,y,z,c) (*(T(*)[x][y][z][c])ptr)
#define NPTR2ARR5D(T,ptr,x,y,z,a,b) (*(T(*)[x][y][z][a][b])ptr)
#define NARR2PTR(T,arr) ((T(*))arr)

#ifdef __cplusplus
extern "C"
{
#endif

  extern double NPI, NDEG2RAD, NRAD2DEG, NEPSILON0, NZEROTHRESHOLD, NMU0;

#ifdef __cplusplus
}
#endif

#endif /*__CONTROLFILE_H__*/
