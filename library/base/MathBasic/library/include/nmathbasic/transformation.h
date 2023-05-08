

#ifndef __NMATHBASICTRANSFORM_H__
#define __NMATHBASICTRANSFORM_H__

#include <nmathbasic/exports.h>
#include <nmathbasic/errors.h>


#ifdef __cplusplus
extern "C"{
#endif

  NMATHBASICPUBFUN  double NMATHBASICCALL n_unit_cell_volume(double a, double b, double c, double alpha, double beta, double gamma);
  NMATHBASICPUBFUN  double NMATHBASICCALL n_parallelogram_area(double a, double b, double alpha);

  NMATHBASICPUBFUN  void NMATHBASICCALL n_transformation_matrix_by_coordinate(double Q[3][3], double x1[3], double y1[3], double z1[3]);
  NMATHBASICPUBFUN  void NMATHBASICCALL n_transformation_matrix_by_eular(double Q[3][3], double z1, double x1, double z2);
  NMATHBASICPUBFUN  void NMATHBASICCALL n_transformation_matrix_by_tait_bryan(double Q[3][3], double x, double y, double z);
  NMATHBASICPUBFUN  void NMATHBASICCALL n_transformation_matrix_lattice_to_crystal(double Q[3][3], double a, double b, double c, double alpha, double beta, double gamma);
  NMATHBASICPUBFUN  void NMATHBASICCALL n_transformation_matrix_crystal_to_lab(double Q[3][3], double axis[3], double angle);
  NMATHBASICPUBFUN  void NMATHBASICCALL n_transformation_matrix_axis_angle(double Q[3][3], double axis[3], double angle);





#ifdef __cplusplus
}
#endif
#endif 
