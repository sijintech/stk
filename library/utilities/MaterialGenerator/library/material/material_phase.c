#include "niobasic/niobasic.h"
#include "nmaterialgenerator/material.h"
#include "nmathbasic/nmathbasic.h"
// #include "symmetry.c"
#include <math.h>

// extern PGConstrain PGRank4Constrain[32];

// xpath is the path to the specific phase
void n_material_generator_one_phase_f(double** tensor,
                                      const char* filename,
                                      const char* xpath,
                                      const char* tensorname) {
    n_material_generator_one_phase(*tensor, filename, xpath, tensorname);
}

/**
 * @brief
 *
 * @param tensor
 * @param filename
 * @param xpath
 * @param tensorname
 * @detail For isostropic material, we support rank 4 (elastic) and rank 2
 * you can define "young" and "poisson" for the index tag in component for
 * rank 4 elastic tensor. For rank 2 tensor, you don't need to define index
 * , just the value tag is enough.
 */
void n_material_generator_one_phase(double* tensor,
                                    const char* filename,
                                    const char* xpath,
                                    const char* tensorname) {
    char xpathText[MAX_STRING - 100] = {'\0'};
    char temp[MAX_STRING] = {'\0'};

    // char material_format[10] = {'\0'};
    // char structure_format[10] = {'\0'};
    char tensor_name[MAX_STRING] = {'\0'};
    int tensor_count = 0;
    // int phase_count = 0, label = 0;
    // int rank = 2;
    // int tensor_index = 0;

    sprintf(xpathText, "%s%s", xpath, "/tensor");
    tensor_count = n_get_xml_element_count(filename, xpathText, "");
                ZF_LOGI("The tensor count %i",tensor_count);

    // rank = n_material_get_tensor_rank(filename, xpathText, tensorname);

    // sprintf(temp, "%s%s", xpath, "/tensor/rank");
    // rank = n_get_xml_element_as_int(filename, temp, "", 4);
    size_t j = 0;

    for (j = 0; j < tensor_count; j++) {
        sprintf(temp, "%s%s%zu%s", xpathText, "[", j + 1, "]/name");
                        ZF_LOGI("The tensor is %s",temp);

        n_get_xml_element_as_string(
            tensor_name, filename, temp, "", "tensorname");
                ZF_LOGI("The tensor is %s",tensor_name);

        if (strcmp(tensor_name, tensorname) == 0) {

            sprintf(temp, "%s%s%zu%s", xpathText, "[", j + 1, "]");
            n_material_generator_one_tensor(tensor, filename, temp);
        }
    }
}