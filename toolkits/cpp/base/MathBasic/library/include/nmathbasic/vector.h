

#ifndef __NMATHBASICVECTOR_H__
#define __NMATHBASICVECTOR_H__

#include <nmathbasic/exports.h>
#include <nmathbasic/errors.h>


#ifdef __cplusplus
extern "C"{
#endif


  NMATHBASICPUBFUN  int NMATHBASICCALL n_vector3_is_parallel(double a[3], double b[3]);
  NMATHBASICPUBFUN  int NMATHBASICCALL n_vector3_is_perpendicular(double a[3], double b[3]);


NMATHBASICPUBFUN void NMATHBASICCALL n_vector3_normalize(double output[3],
                                                      double a[3]);
NMATHBASICPUBFUN void NMATHBASICCALL n_vector3_normalize_inplace(double a[3]);

  NMATHBASICPUBFUN  double NMATHBASICCALL n_vector3_norm(double a[3]);
  NMATHBASICPUBFUN  double NMATHBASICCALL n_vector3_dot_vector3(double a[3], double b[3]);
  NMATHBASICPUBFUN  void NMATHBASICCALL n_vector3_cross_vector3(double output[3], double a[3], double b[3]);


#ifdef __cplusplus
}
#endif
#endif 
