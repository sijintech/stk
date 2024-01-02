#include "mkl.h"
#include "nmathbasic/nmathbasic.h"

void n_tensor3333_to_tensor99(double out[9][9], double in[3][3][3][3])
{
    int map[3][3] = {{0, 1, 2}, {3, 4, 5}, {6, 7, 8}};
    size_t i = 0;
    size_t j = 0;
    size_t k = 0;
    size_t l = 0;
    for (i = 0; i < 3; i++)
    {
        for (j = 0; j < 3; j++)
        {
            for (k = 0; k < 3; k++)
            {
                for (l = 0; l < 3; l++)
                {
                    out[map[i][j]][map[k][l]] = in[i][j][k][l];
                }
            }
        }
    }
}

void n_tensor3333_to_tensor66(double out[6][6], double in[3][3][3][3])
{
    // ZF_LOGI("inside %x %x %f", in, (*in), (*in)[0][0][0][0]);

    int map[3][3] = {{0, 5, 4}, {5, 1, 3}, {4, 3, 2}};
    size_t i = 0;
    size_t j = 0;
    size_t k = 0;
    size_t l = 0;
    for (i = 0; i < 3; i++)
    {
        for (j = 0; j < 3; j++)
        {
            for (k = 0; k < 3; k++)
            {
                for (l = 0; l < 3; l++)
                {
                    if (k != l)
                    {
                        out[map[i][j]][map[k][l]] =
                            in[i][j][k][l] + in[i][j][l][k];
                    }
                    else
                    {
                        out[map[i][j]][map[k][l]] = in[i][j][k][l];
                    }
                    // ZF_LOGI("33 to 66 %i %i %i %i %f %f
                    // %f",i,j,k,l,in[i][j][k][l],in[i][j][l][k],out[map[i][j]][map[k][l]]);
                }
            }
        }
    }
}

void n_tensor99_to_tensor3333(double out[3][3][3][3], double in[9][9])
{
    int map_row[9] = {0, 0, 0, 1, 1, 1, 2, 2, 2};
    int map_col[9] = {0, 1, 2, 0, 1, 2, 0, 1, 2};
    size_t i = 0;
    size_t j = 0;
    for (i = 0; i < 9; i++)
    {
        for (j = 0; j < 9; j++)
        {
            out[map_row[i]][map_col[i]][map_row[j]][map_col[j]] = in[i][j];
        }
    }
}

void n_tensor66_to_tensor3333(double out[3][3][3][3], double in[6][6])
{
    int map_row[6] = {0, 1, 2, 1, 0, 0};
    int map_col[6] = {0, 1, 2, 2, 2, 1};
    size_t i = 0;
    size_t j = 0;
    for (i = 0; i < 6; i++)
    {
        for (j = 0; j < 6; j++)
        {
            if (j < 3)
            {
                out[map_row[i]][map_col[i]][map_row[j]][map_col[j]] = in[i][j];
                out[map_col[i]][map_row[i]][map_row[j]][map_col[j]] = in[i][j];
                out[map_col[i]][map_row[i]][map_col[j]][map_row[j]] = in[i][j];
                out[map_row[i]][map_col[i]][map_col[j]][map_row[j]] = in[i][j];
            }
            else
            {
                out[map_row[i]][map_col[i]][map_row[j]][map_col[j]] =
                    0.5 * in[i][j];
                out[map_col[i]][map_row[i]][map_row[j]][map_col[j]] =
                    0.5 * in[i][j];
                out[map_col[i]][map_row[i]][map_col[j]][map_row[j]] =
                    0.5 * in[i][j];
                out[map_row[i]][map_col[i]][map_col[j]][map_row[j]] =
                    0.5 * in[i][j];
            }
        }
    }
}

void n_matrix_square_inverse(int N, double* A)
{
    lapack_int* IPIV;
    IPIV = (lapack_int*)calloc(N, sizeof(lapack_int));
    lapack_int NN = N;
    // double AA[N][N];
    // for(int i=0;i<N;i++){
    //     for(int j=0;j<N;j++){
    //         AA[i][j]=A[i*N+j];
    //     }
    // }
    // int LWORK = N * N;
    // double WORK[LWORK];
    // int INFO;
    // ZF_LOGI("before dgetrf %i %i",N,NN);//,AA[0][0]);
    // for(int i=0;i<36;i++){
    //         ZF_LOGI(" %i %f",i,A[i]);
    // }
    // dgetrf_( &N, &N, A, &N, IPIV, &INFO);
    // dgetri_( &N, A, &N, IPIV, WORK, &LWORK, &INFO);
    lapack_int info = LAPACKE_dgetrf(LAPACK_ROW_MAJOR, NN, NN, A, NN, IPIV);
    // ZF_LOGI("after dgetrf %i %i %f %i %i", N, NN, A[0], info, sizeof(IPIV));
    // for (int i = 0; i < 36; i++)
    // {
    //     ZF_LOGI(" %i %f", i, A[i]);
    // }
    // for (int i = 0; i < 6; i++)
    // {
    //     ZF_LOGI(" %i %li", i, IPIV[i]);
    // }
    // NN = N;
    info = LAPACKE_dgetri(LAPACK_ROW_MAJOR, NN, A, NN, IPIV);
    // ZF_LOGI("after dgetrf %i %i %f %i", N, NN, A[0], info);
    // for (int i = 0; i < 36; i++)
    // {
    //     ZF_LOGI("after %i %f", i, A[i]);
    // }
    // ZF_LOGI("%i ",N);
    // ZF_LOGI("%i ",LAPACK_ROW_MAJOR);
    // ZF_LOGI("%f ",AA[0][0]);
    // NN = N;
    // ZF_LOGI("after LAPACKE_dgetri %i %f %i ", info, A[0], NN);
}

void n_tensor3333_inverse99(double out[3][3][3][3], double in[3][3][3][3])
{
    double temp[9][9] = {0};
    n_tensor3333_to_tensor99(temp, in);
    n_matrix_square_inverse(9, NARR2PTR(double, temp));
    n_tensor99_to_tensor3333(out, temp);
}

void n_tensor3333_inverse66(double out[3][3][3][3], double in[3][3][3][3])
{
    double temp[6][6] = {0};
    double(*in_ptr)[3][3][3][3];
    double(*temp_ptr)[6][6];
    in_ptr = &NPTR2ARR4D(double, in, 3, 3, 3, 3);
    temp_ptr = &NPTR2ARR2D(double, temp, 6, 6);
    // for (int i = 0; i < 3; i++)
    // {
    //     for (int j = 0; j < 3; j++)
    //     {

    //         ZF_LOGI("temp %i %i %f",i,j,temp[i][j]);

    //         for (int k = 0; k < 3; k++)
    //         {
    //             for (int l = 0; l < 3; l++)
    //             {
    //                 ZF_LOGI("in %i %i %i %i %f
    //                 %f",i,j,k,l,in[i][j][k][l],(*in_ptr)[i][j][k][l]);
    //             }
    //         }
    //     }
    // }
    // ZF_LOGI("outside %x %x %f %f", in_ptr, (*in_ptr), (*in_ptr)[0][0][0][0],
    // in_ptr[0][0][0][0]); ZF_LOGI("outside %x %x %f %f", temp_ptr,
    // (*temp_ptr), (*temp_ptr)[0][0], temp_ptr[0][0]);
    n_tensor3333_to_tensor66(temp, in);
    // ZF_LOGI("outside after %x %x %x %f %f", temp, temp_ptr, (*temp_ptr),
    // (*temp_ptr)[0][0], temp_ptr[0][0]);

    //     for(int i=0;i<6;i++){
    //         for(int j=0;j<6;j++){
    //         ZF_LOGI("temp %i %i %f",i,j,temp[i][j]);
    //         }
    // }
    n_matrix_square_inverse(6, NARR2PTR(double, temp));
    n_tensor66_to_tensor3333(out, temp);
}

void n_tensor3333_mult_tensor33(double out[3][3], double A[3][3][3][3],
                                double B[3][3])
{
    size_t i = 0;
    size_t j = 0;
    size_t k = 0;
    size_t l = 0;
    for (i = 0; i < 3; i++)
    {
        for (j = 0; j < 3; j++)
        {
            out[i][j] = 0;
            for (k = 0; k < 3; k++)
            {
                for (l = 0; l < 3; l++)
                {
                    out[i][j] = out[i][j] + A[i][j][k][l] * B[k][l];
                }
            }
        }
    }
}

void n_tensor_rank4_print_screen(const char* name, double* input)
{
    ZF_LOGI("---------Begin 4th rank tensor %s-------------", name);
    char temp[50] = {'\0'};
    char temp3[50] = {'\0'};
    char temp9[150] = {'\0'};
    size_t i = 0;
    size_t j = 0;
    size_t k = 0;
    size_t l = 0;
    for (i = 0; i < 3; i++)
    {
        for (j = 0; j < 3; j++)
        {
            temp9[0] = '\0';
            for (k = 0; k < 3; k++)
            {
                temp3[0] = '\0';
                for (l = 0; l < 3; l++)
                {
                    sprintf(temp, "%zu%zu%zu%zu = %13.6le", i + 1, j + 1, k + 1,
                            l + 1, input[27 * i + 9 * j + 3 * k + l]);
                    n_string_join(temp3, temp3, temp, " ");
                }
                n_string_join(temp9, temp9, temp3, " ");
            }
            ZF_LOGI("%s", temp9);
        }
    }
    ZF_LOGI("--------- End 4th rank tensor %s -------------", name);
}

void n_tensor_rank4_print_file(const char* name, double* input)
{
    FILE* fp;
    char temp[512] = {'\0'};
    char temp9[1024] = {'\0'};
    fp = fopen(name, "w");
    fprintf(fp, "Index,11,12,13,21,22,23,31,32,33\n");
    size_t i = 0;
    size_t j = 0;
    size_t k = 0;
    size_t l = 0;
    for (i = 0; i < 3; i++)
    {
        for (j = 0; j < 3; j++)
        {
            temp9[0] = '\0';
            sprintf(temp9, "%zu%zu", i + 1, j + 1);
            for (k = 0; k < 3; k++)
            {
                for (l = 0; l < 3; l++)
                {
                    sprintf(temp, ",%13.6le",
                            input[27 * i + 9 * j + 3 * k + l]);
                    strcat(temp9, temp);
                }
            }
            fprintf(fp, "%s\n", temp9);
        }
    }
    fclose(fp);
}