#include "nmathbasic/nmathbasic.h"

/**
 * Get the transformation matrix of Q=a.b
 *
 */
void n_matrix33_multiplication(double output[3][3], double a[3][3],
                                 double b[3][3]) {
  size_t i = 0;
  size_t j = 0;
  for (i = 0; i < 3; i++) {
    for (j = 0; j < 3; j++) {
      output[i][j] = a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j];
    }
  }
}

double n_matrix33_determinant(double a[3][3]) {
  return a[0][0] * a[1][1] * a[2][2] + a[0][1] * a[1][2] * a[2][0] +
         a[0][2] * a[1][0] * a[2][1] - a[0][2] * a[1][1] * a[2][0] -
         a[0][1] * a[1][0] * a[2][2] - a[0][0] * a[1][2] * a[2][1];
}

void n_matrix33_inverse(double output[3][3], double a[3][3]) {
  double determinant = n_matrix33_determinant(a);
  size_t i = 0;
  size_t j = 0;
  if (fabs(determinant)<1e-16)
  {
    for (i = 0; i < 3; i++)
    {
      for (j = 0; j < 3; j++)
      {
        output[i][j]=0;
      } 
    }
  }else{
    output[0][0] = (a[1][1] * a[2][2] - a[1][2] * a[2][1]) / determinant;
    output[0][1] = -(a[0][1] * a[2][2] - a[0][2] * a[2][1]) / determinant;
    output[0][2] = (a[0][1] * a[1][2] - a[0][2] * a[1][1]) / determinant;

    output[1][0] = -(a[1][0] * a[2][2] - a[1][2] * a[2][0]) / determinant;
    output[1][1] = (a[0][0] * a[2][2] - a[0][2] * a[2][0]) / determinant;
    output[1][2] = -(a[0][0] * a[1][2] - a[0][2] * a[1][0]) / determinant;

    output[2][0] = (a[1][0] * a[2][1] - a[1][1] * a[2][0]) / determinant;
    output[2][1] = -(a[0][0] * a[2][1] - a[0][1] * a[2][0]) / determinant;
    output[2][2] = (a[0][0] * a[1][1] - a[0][1] * a[1][0]) / determinant;
  }
  
}

void n_matrix33_print(const char *name, double input[3][3]) {
  ZF_LOGI("---------- %s Begin ----------", name);
  ZF_LOGI("| %6.2f %6.2f %6.2f", input[0][0], input[0][1], input[0][2]);
  ZF_LOGI("| %6.2f %6.2f %6.2f", input[1][0], input[1][1], input[1][2]);
  ZF_LOGI("| %6.2f %6.2f %6.2f", input[2][0], input[2][1], input[2][2]);
  ZF_LOGI("----------- %s End -----------", name);
}