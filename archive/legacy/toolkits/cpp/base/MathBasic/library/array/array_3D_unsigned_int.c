#include "nmathbasic/nmathbasic.h"

void n_data_3D_unsigned_int_init(int x, int y, int z, unsigned int (**outptr)[x][y][z]) {
  *outptr = calloc(x*y*z,sizeof(unsigned int));
}

void n_data_3D_unsigned_int_fill(int x, int y, int z, unsigned int array[x][y][z]) {
  unsigned count = 0;
  size_t i = 0;
  size_t j = 0;
  size_t k = 0;
  for (i = 0; i < x; i++) {
    for (j = 0; j < y; j++) {
      for (k = 0; k < z; k++) {
        array[i][j][k] = count;
        count++;
      }
    }
  }
}

void n_data_3D_unsigned_int_assign(int x, int y, int z, unsigned int array[x][y][z], unsigned int value) {
  size_t i = 0;
  size_t j = 0;
  size_t k = 0;
  for (i = 0; i < x; i++) {
    for (j = 0; j < y; j++) {
      for (k = 0; k < z; k++) {
        array[i][j][k] = value;
      }
    }
  }
}

void n_data_3D_unsigned_int_print(int x, int y, int z, unsigned int array[x][y][z]) {
  size_t i = 0;
  size_t j = 0;
  size_t k = 0;
  for (i = 0; i < x; i++) {
    for (j = 0; j < y; j++) {
      for (k = 0; k < z; k++) {
        ZF_LOGI("i:%zu j:%zu k:%zu val:%u", i, j, k, array[i][j][k]);
      }
    }
  }
}

int n_data_3D_unsigned_int_equal_count(int x, int y, int z, unsigned int array[x][y][z],
                              unsigned int value) {
  int count = 0;
  size_t i = 0;
  size_t j = 0;
  size_t k = 0;
  for (i = 0; i < x; i++) {
    for (j = 0; j < y; j++) {
      for (k = 0; k < z; k++) {
        if (array[i][j][k] == value) {
          count = count + 1;
        }
      }
    }
  }
  return count;
}

int n_data_3D_unsigned_int_not_equal_count(int x, int y, int z, unsigned int array[x][y][z],
                                  unsigned int value) {
  int count = 0;
  size_t i = 0;
  size_t j = 0;
  size_t k = 0;
  for (i = 0; i < x; i++) {
    for (j = 0; j < y; j++) {
      for (k = 0; k < z; k++) {
        if (array[i][j][k] != value) {
          count = count + 1;
        }
      }
    }
  }
  return count;
}

void n_data_3D_unsigned_int_exist_range_f(int **out, int *x, int *y, int *z, unsigned int **array,
                                 unsigned int *value) {
  n_data_3D_unsigned_int_exist_range(*out, *x, *y, *z, NPTR2ARR3D(unsigned int,*array,*x, *y, *z), *value);
}
void n_data_3D_unsigned_int_exist_range(int out[6], int x, int y, int z,
                               unsigned int array[x][y][z], unsigned int value) {
  int xmin = x, xmax = 0;
  int ymin = y, ymax = 0;
  int zmin = z, zmax = 0;
  int flag = 0;
  size_t i = 0;
  size_t j = 0;
  size_t k = 0;
  for (i = 0; i < x; i++) {
    for (j = 0; j < y; j++) {
      for (k = 0; k < z; k++) {
        if (array[i][j][k] == value) {
          flag = 1;
          if (i < xmin)
            xmin = i;
          if (i > xmax)
            xmax = i;
          if (j < ymin)
            ymin = j;
          if (j > ymax)
            ymax = j;
          if (k < zmin)
            zmin = k;
          if (k > zmax)
            zmax = k;
        }
      }
    }
  }
  if (flag == 1) {
    out[0] = xmin;
    out[1] = xmax;
    out[2] = ymin;
    out[3] = ymax;
    out[4] = zmin;
    out[5] = zmax;
  } else {
    out[0] = 0;
    out[1] = 0;
    out[2] = 0;
    out[3] = 0;
    out[4] = 0;
    out[5] = 0;
  }
}