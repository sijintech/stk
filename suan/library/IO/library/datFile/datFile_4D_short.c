#include "niobasic/datFile.h"

void n_datFile_4D_short_read_f(int *x, int *y, int *z, int *c, short **data, const char *file){
    n_datFile_4D_short_read(*x, *y, *z, *c, NPTR2ARR4D(short,*data,*x, *y, *z, *c), file);
}
void n_datFile_4D_short_read(int x, int y, int z, int c, short data[x][y][z][c], const char *file)
{
    char line_buf[1024];
    char *temp;
    // size_t line_buf_size = 0;
    // ssize_t line_size;
    int ii = 0, jj = 0, kk = 0, ll = 0;
    // int fhi = 0;
    int offset = 0;
    FILE *fp = fopen(file, "r");
    if (!fp)
    {
        fprintf(stderr, "Error opening file '%s'\n", file);
    }
    fgets(line_buf, sizeof(line_buf), fp);
    sscanf(line_buf, "%i %i %i %i", &ii, &jj, &kk, &ll);
    // for (size_t i = 0; i < nx*ny*nz; i++)
    while (fgets(line_buf, sizeof(line_buf), fp) != NULL)
    {
        // fgets(line_buf, sizeof(line_buf), fp);
        temp = line_buf;
        sscanf(temp, "%i %i %i%n", &ii, &jj, &kk, &offset);
        temp = temp + offset;
        for (ll = 0; ll < c; ll++)
        {
            sscanf(temp, "%hu%n", &data[ii-1][jj-1][kk-1][ll], &offset);
        }
    }
    fclose(fp);
}

void n_datFile_4D_short_write_f(int *x, int *y, int *z, int *c, short **data, const char *file){
    n_datFile_4D_short_write(*x,*y,*z,*c, NPTR2ARR4D(short,*data,*x,*y,*z,*c), file);
}
void n_datFile_4D_short_write(int x, int y, int z, int c, short data[x][y][z][c], const char *file){
    remove(file);
    FILE *fp = fopen(file,"w");
    char *line=NULL;
    // size_t len=0;
    // ssize_t read;
    // First line of the file is for dimensions
    fprintf(fp,MY_DAT_HEAD_FORMAT,x,y,z,c);
    int i=0;
    int j=0;
    int k=0;
    int l=0;
    for (i = 0; i < x; i++){
        for (j = 0; j < y; j++){
            for (k = 0; k < z; k++){
                fprintf(fp,MY_DAT_CORD_FORMAT,i+1,j+1,k+1);
                for (l = 0; l < c; l++){
                    fprintf(fp,MY_DAT_FORMAT_short,data[i][j][k][l]);
                }
                fprintf(fp,"\n");
            }
        }
    }
    fclose(fp);
    if(line)free(line);
}