#ifndef __NMATHBASICFILTER_H__
#define __NMATHBASICFILTER_H__

#include <nmathbasic/errors.h>
#include <nmathbasic/exports.h>
#include <ntextutils/ntextutils.h>

#ifdef __cplusplus__
extern "C" {
#endif

NMATHBASICPUBFUN void NMATHBASICCALL n_filter_neighbour_1st(
    int nx, int ny, int nx, int output[nx][ny][nz], int input[nx][ny][nz]);
// NMATHBASICPUBFUN void NMATHBASICCALL filter_neighbour_2nd(
    // int nx, int ny, int nx, int output[nx][ny][nz], int input[nx][ny][nz]);

#ifdef __cplusplus__
}
#endif

#endif