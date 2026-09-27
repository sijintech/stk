#ifndef __NMATHBASICMATRIX_H__
#define __NMATHBASICMATRIX_H__

#include <nmathbasic/errors.h>
#include <nmathbasic/exports.h>

#ifdef __cplusplus
extern "C" {
#endif

NMATHBASICPUBFUN void NMATHBASICCALL n_matrix33_multiply_vector3(double output[3],
                                                               double Q[3][3],
                                                               double input[3]);
NMATHBASICPUBFUN void NMATHBASICCALL n_matrix33_multiply_matrix33(double Q[3][3],
                                                                double a[3][3],
                                                                double b[3][3]);

NMATHBASICPUBFUN void NMATHBASICCALL n_matrix33_inverse(double output[3][3],
                                                          double a[3][3]);
NMATHBASICPUBFUN void NMATHBASICCALL n_matrix33_print(const char *name,
                                                    double input[3][3]);

NMATHBASICPUBFUN void NMATHBASICCALL get_matrix22_inverse(double output[2][2], double input[2][2]);


#ifdef __cplusplus
}
#endif
#endif
