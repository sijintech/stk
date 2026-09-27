#include <math.h>
#include <niobasic/niobasic.h>
#include <nmaterialgenerator/material.h>
#include <nmathbasic/nmathbasic.h>

void n_material_tensor_print(double* tensor, int rank, const char* name) {

    size_t i = 0;
    size_t j = 0;
    size_t k = 0;
    size_t l = 0;
    if (rank == 0) {
        ZF_LOGI("---------Begin Scalar %s-------------", name);
        ZF_LOGI("%s =%13.6le", name, tensor[0]);
        ZF_LOGI("--------- End Scalar %s -------------", name);
    } else if (rank == 1) {
        ZF_LOGI("---------Begin Vector %s-------------", name);
        ZF_LOGI("1 =%13.6le 2 =%13.6le 3 =%13.6le",
                tensor[0],
                tensor[1],
                tensor[2]);
        ZF_LOGI("--------- End Vector %s -------------", name);
    } else if (rank == 2) {
        ZF_LOGI("---------Begin 2nd rank tensor %s-------------", name);
        for (i = 0; i < 3; i++) {
            ZF_LOGI("%zu1 =%13.6le %zu2 =%13.6le %zu3 =%13.6le",
                    i + 1,
                    tensor[3 * i],
                    i + 1,
                    tensor[3 * i + 1],
                    i + 1,
                    tensor[3 * i + 2]);
        }
        ZF_LOGI("--------- End 2nd rank tensor %s -------------", name);
    } else if (rank == 4) {
        ZF_LOGI("---------Begin 4th rank tensor %s-------------", name);
        char temp[MAX_STRING] = {'\0'};
        char temp3[MAX_STRING] = {'\0'};
        char temp9[MAX_STRING] = {'\0'};
        for (i = 0; i < 3; i++) {
            for (j = 0; j < 3; j++) {
                temp9[0] = '\0';
                for (k = 0; k < 3; k++) {
                    temp3[0] = '\0';
                    for (l = 0; l < 3; l++) {
                        sprintf(temp,
                                "%zu%zu%zu%zu=%9.2le",
                                i + 1,
                                j + 1,
                                k + 1,
                                l + 1,
                                tensor[27 * i + 9 * j + 3 * k + l]);
                        n_string_join(temp3, temp3, temp, " ");
                    }
                    n_string_join(temp9, temp9, temp3, " ");
                }
                ZF_LOGI("%s", temp9);
            }
        }
        ZF_LOGI("--------- End 4th rank tensor %s -------------", name);
    }
}

void n_material_tensor_distribution_print(const char* name,
                                          int nx,
                                          int ny,
                                          int nz,
                                          short* eta,
                                          int rank,
                                          double* tensor,
                                          const char* index) {
    int tensor_index = 0;
    int tensor_total = pow(3, rank);
    tensor_index = n_material_index_string_to_int(index);
    char filename[NAME_STRING];
    n_string_concat(filename, 4, name, "_", index, ".vti");

    double* data = malloc(sizeof(double) * nx * ny * nz);
    size_t i = 0;
    for (i = 0; i < nx * ny * nz; i++) {
        data[i] = tensor[eta[i] * tensor_total + tensor_index];
    }

    n_vtiFile_3D_double_write(
        nx, ny, nz, NPTR2ARR3D(double, data, nx, ny, nz), filename);
    free(data);
}