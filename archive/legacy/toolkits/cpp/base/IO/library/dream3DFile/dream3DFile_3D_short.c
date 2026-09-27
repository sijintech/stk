#include "niobasic/dream3DFile.h"

void n_dream3DFile_3D_short_read_f(
    int* x, int* y, int* z, short** data, const char* file) {
    n_dream3DFile_3D_short_read(
        *x, *y, *z, NPTR2ARR3D(short, *data, *x, *y, *z), file);
}
void n_dream3DFile_3D_short_read(
    int x, int y, int z, short data[x][y][z], const char* file) {
    char line_buf[32];
    char* temp;
    // size_t line_buf_size = 0;
    // ssize_t line_size;
    int ii = 0, jj = 0, kk = 0, count = 0;
    // int fhi = 0;
    int offset = 0;
    FILE* fp = fopen(file, "r");
    if (!fp) {
        fprintf(stderr, "Error opening file '%s'\n", file);
    }
    // for (size_t i = 0; i < nx*ny*nz; i++)
    while (fgets(line_buf, sizeof(line_buf), fp) != NULL && count < x * y * z) {

        ii = count % x;
        jj = ((count - ii) / x) % y;
        kk = (count - ii - jj * x) / x / y;
        sscanf(line_buf, "%hu", &data[ii][jj][kk]);
        count = count + 1;
    }
    fclose(fp);
}
