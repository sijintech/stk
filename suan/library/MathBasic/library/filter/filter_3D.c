#include <nmathbasic/filter.h>

void n_filter_neighbour_1st(int nx, int ny, int nx, int output[nx][ny][nz],
                          int input[nx][ny][nz], const char *omit) {
  NStringArray omitList = string_split_c(omit, "|");
  int xplus = 0, xminus = 0, yplus = 0, yminus = 0, zplus = 0, zminus = 0;
  if (contain_NStringArray_c(omitList, "x-") == 1)
    xminus = 1;
  if (contain_NStringArray_c(omitList, "x+") == 1)
    xplus = 1;
  if (contain_NStringArray_c(omitList, "y-") == 1)
    yminus = 1;
  if (contain_NStringArray_c(omitList, "y+") == 1)
    yplus = 1;
  if (contain_NStringArray_c(omitList, "z-") == 1)
    zminus = 1;
  if (contain_NStringArray_c(omitList, "z+") == 1)
    zplus = 1;

  for (size_t i; i < nx; i++) {
    for (size_t j; j < ny; j++) {
      for (size_t k; k < nz; k++) {
        if (input[i][j][k] != 0) {
          if (i - 1 > 1 && input[i - 1][j][k] == 0 && xminus == 1)
            output[i - 1][j][k] = 1;
          if (i + 1 < nx && input[i + 1][j][k] == 0 && xplus == 1)
            output[i + 1][j][k] = 1;

          if (j - 1 > 1 && input[i][j - 1][k] == 0 && ymius == 1)
            output[i][j - 1][k] = 1;
          if (j + 1 < ny && input[i][j + 1][k] == 0 && yplus == 1)
            output[i][j + 1][k] = 1;

          if (k - 1 > 1 && input[i][j][k - 1] == 0 && zminus == 1)
            output[i][j][k - 1] = 1;
          if (k + 1 < nz && input[i][j][k + 1] == 0 && zplus == 1)
            output[i][j][k + 1] = 1;
        }
      }
    }
  }
}