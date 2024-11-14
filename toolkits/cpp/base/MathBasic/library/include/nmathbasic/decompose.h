

#ifndef __NMATHBASICDECOMPOSE_H__
#define __NMATHBASICDECOMPOSE_H__

#include <nmathbasic/exports.h>
#include <nmathbasic/errors.h>


#ifdef __cplusplus
extern "C"{
#endif

/**
 * The following not correct yet please ignore them
 */
  NMATHBASICPUBFUN  void NMATHBASICCALL n_matrix_multiply_matrix(int m, int n, int o, double out[m][o], double A[m][n], double B[n][o]);
  NMATHBASICPUBFUN  void NMATHBASICCALL n_matrix_transpose(int m, int n, double A[m][n], double B[m][n]);
  NMATHBASICPUBFUN  void NMATHBASICCALL n_matrix_duplicate(int m, int n, double out[m][n], double in[m][n]);
  NMATHBASICPUBFUN  void NMATHBASICCALL n_matrix_minor(int m, int n, double out[m][n], double in[m][n], int d);
  NMATHBASICPUBFUN  void NMATHBASICCALL n_matrix_col(int m, int n, double *v, double in[m][n], int c);
  NMATHBASICPUBFUN  double NMATHBASICCALL n_vector_norm(int n, double *v);

  NMATHBASICPUBFUN  void NMATHBASICCALL n_matrix_pivot(int n, double A[n][n], double P[n][n]);
  NMATHBASICPUBFUN  void NMATHBASICCALL n_matrix_LU_decompose_crout(int n, double A[n][n], double L[n][n], double U[n][n], double P[n][n]);

  NMATHBASICPUBFUN  void NMATHBASICCALL n_matrix_QR_decompose_householder(int m, int n, double Q[m][m], double R[m][n], double M[m][n]);



#ifdef __cplusplus
}
#endif
#endif 



