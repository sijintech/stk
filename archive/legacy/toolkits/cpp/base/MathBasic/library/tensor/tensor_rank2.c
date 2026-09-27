#include "nmathbasic/nmathbasic.h"

void n_tensor_rank2_from_voigt_f(int *x, int *y, int *z, double **voigt, double **tensor, int *isStrain)
{
    n_tensor_rank2_from_voigt(*x, *y, *z, NPTR2ARR4D(double,*voigt,*x, *y, *z,6), NPTR2ARR5D(double,*tensor,*x, *y, *z,3,3), *isStrain);
}

void n_tensor_rank2_from_voigt(int x, int y, int z, double voigt[x][y][z][6], double tensor[x][y][z][3][3], int isStrain)
{
    double multiplier = 1.0;
    if (isStrain)
    {
        multiplier = 0.5;
    }
    int i = 0;
    int j = 0;
    int k = 0;
    for (i = 0; i < x; i++)
    {
        for (j = 0; j < y; j++)
        {
            for (k = 0; k < z; k++)
            {
                tensor[i][j][k][0][0] = voigt[i][j][k][0];
                tensor[i][j][k][1][1] = voigt[i][j][k][1];
                tensor[i][j][k][2][2] = voigt[i][j][k][2];
                tensor[i][j][k][1][2] = voigt[i][j][k][3] * multiplier;
                tensor[i][j][k][0][2] = voigt[i][j][k][4] * multiplier;
                tensor[i][j][k][0][1] = voigt[i][j][k][5] * multiplier;

                tensor[i][j][k][2][1] = voigt[i][j][k][3] * multiplier;
                tensor[i][j][k][2][0] = voigt[i][j][k][4] * multiplier;
                tensor[i][j][k][1][0] = voigt[i][j][k][5] * multiplier;
            }
        }
    }
}

void n_tensor_rank2_to_voigt_f(int *x, int *y, int *z, double **tensor, double **voigt, int *isStrain)
{
    n_tensor_rank2_to_voigt(*x, *y, *z, NPTR2ARR5D(double, *tensor,*x,*y,*z,3,3), NPTR2ARR4D(double, *voigt,*x,*y,*z,6), *isStrain);
}

void n_tensor_rank2_to_voigt(int x, int y, int z, double tensor[x][y][z][3][3], double voigt[x][y][z][6], int isStrain)
{
    double multiplier = 1.0;
    if (isStrain)
    {
        multiplier = 2.0;
    }
    int i = 0;
    int j = 0;
    int k = 0;
    for (i = 0; i < x; i++)
    {
        for (j = 0; j < y; j++)
        {
            for (k = 0; k < z; k++)
            {
                voigt[i][j][k][0] = tensor[i][j][k][0][0];
                voigt[i][j][k][1] = tensor[i][j][k][1][1];
                voigt[i][j][k][2] = tensor[i][j][k][2][2];
                voigt[i][j][k][3] = tensor[i][j][k][1][2] * multiplier;
                voigt[i][j][k][4] = tensor[i][j][k][0][2] * multiplier;
                voigt[i][j][k][5] = tensor[i][j][k][0][1] * multiplier;
            }
        }
    }
}

void n_tensor_rank2_print_screen(const char *name, double *input)
{
    ZF_LOGI("---------- %s Begin ----------", name);
    ZF_LOGI("| %6.2f %6.2f %6.2f", input[0], input[1], input[2]);
    ZF_LOGI("| %6.2f %6.2f %6.2f", input[3], input[4], input[5]);
    ZF_LOGI("| %6.2f %6.2f %6.2f", input[6], input[7], input[8]);
    ZF_LOGI("----------- %s End -----------", name);
}

void n_tensor_rank2_print_file(const char *name, double *input)
{
    FILE *fp;
    // char temp[50] = {'\0'};
    // char temp3[50] = {'\0'};
    fp = fopen(name, "w");
    fprintf(fp, "Index,1,2,3\n");
    size_t i=0;
    for (i = 0; i < 3; i++)
    {
        fprintf(fp, "%zu,%+13.6le,%+13.6le,%+13.6le\n", i + 1, input[3*i], input[3*i+1], input[3*i+2]);
    }
    fclose(fp);
}