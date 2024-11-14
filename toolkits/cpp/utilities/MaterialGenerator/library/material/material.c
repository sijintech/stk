/**
 * @file nstructure-generator/material/material.c
 * @author Xiaoxing Cheng
 * @date 2021/02/07
 * @brief For the purpose of preparing the tensor for solvers based on given
 * structure The primary feature is the most memory efficient way of 3D array
 * allocation, which only malloc array that have a different value. To take
 * symmetry or specific rules into consideration, it is done afterwards, using
 * rules from the nmath-basic library, or done directly in main programs.
 */

#include "niobasic/niobasic.h"
#include "nmathbasic/nmathbasic.h"
#include <nmaterialgenerator/material.h>
// #include "symmetry.c"
#include <math.h>

// Material means phase distribution + property for each phase
// or the property distribution directly
// pointer to an array of tensor components, which is a 3D array
/**
 * @page n_material_generator
 * @param[out] double** tensor The array of pointers, each points toward one
 * tensor component
 * @param[in] char* filename The name for the xml input file.
 * @param[in] char* xpath The xpath path to the "material" tag.
 * @param[in] char* tensorname The name of the tensor that we want to assign
 * within the current materials tag.
 * @param[in] int[nx][ny][nz] eta The phase distribution
 * @details The tensor is a 2D array, with row means number of phases, column
 * means number of tensor components. But the flattened tensor for each phase as
 * 1D array is not easy to use. We can assign a pointer to an double array with
 * the correct dimension, and when allocate such array as if it is a 2D array.
 * Since the memory are continuous, the results are still correct.
 * double(*tensor)[phase_count][3][3];
 * n_data_2D_double_init(phase_count,9,&tensor);
 * Then whenever we use the tensor, simply use (*tensor)[phase_index][i][j]
 */
void n_material_generator_f(double** tensor,
                            const char* filename,
                            const char* xpath,
                            const char* tensorname) {
    n_material_generator(*tensor, filename, xpath, tensorname);
}
void n_material_generator(double* tensor,
                          const char* filename,
                          const char* xpath,
                          const char* tensorname) {
    char xpathText[MAX_STRING - 100] = {'\0'};
    // char temp[MAX_STRING] = {'\0'};
    //  char equal_string[10] = {'\0'};
    //  char index_string[10] = {'\0'};
    char material_format[10] = {'\0'};
    // char structure_format[10] = {'\0'};
    // char tensor_name[MAX_STRING] = {'\0'};
    // char point_group[10] = "custom";
    // NStringArray tt;
    // int tensor_count = 0;
    // int component_count = 0;
    int phase_count = 0;
    // int label = 0;
    int rank = 2;
    // int equal_count = 0, sign = 1, tensor_index = 0;
    // int count = 0;
    // double value;
    n_string_join(xpathText, xpath, "/format", "");
    n_get_xml_element_as_string(
        material_format, filename, xpathText, "", "xml");
    // ZF_LOGI("The format is %s %s",xpathText,material_format);
    if (strcmp(material_format, "xml") == 0) {
        // first get the eta
        // then assign for the tensor
        // get the value count
        n_string_join(xpathText, xpath, "/phase", "");
        phase_count = n_get_xml_element_count(filename, xpathText, "");

        n_string_join(xpathText, xpath, "/phase[1]/tensor", "");
        rank = n_material_get_tensor_rank(filename, xpathText, tensorname);

        double(*tensor_temp)[phase_count][(int)(pow(3, rank) + 0.5)];
        tensor_temp =
            &NPTR2ARR2D(double, tensor, phase_count, (int)(pow(3, rank) + 0.5));
        size_t i = 0;
        for (i = 0; i < phase_count; i++) {
            sprintf(xpathText, "%s%s%zu%s", xpath, "/phase[", i + 1, "]");
    // ZF_LOGI("The rank is %i %s",rank,xpathText);
            n_material_generator_one_phase(
                (double*)&(*tensor_temp)[i], filename, xpathText, tensorname);
        }
    } else if (strcmp(material_format, "csv") == 0) {
        ZF_LOGI("For now we only support xml, not csv");
    }
}
