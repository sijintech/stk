
#include <math.h>
#include <niobasic/niobasic.h>
#include <nmaterialgenerator/material.h>
#include <nmathbasic/nmathbasic.h>

extern PointGroup PGRank4[32];
extern PointGroup IsotropicRank4;
// based on the Schoenfilies notation from
// https://en.wikipedia.org/wiki/Crystallographic_point_group

int n_material_index_string_to_int(const char* equal_string) {
    char temp[10] = {'\0'};
    strcpy(temp, equal_string);
    // ZF_LOGI("The string %s %s",equal_string,temp);

    n_string_reverse_in_place(temp);
    // ZF_LOGI("The string after %s %s",equal_string,temp);

    int tensor_index = 0;
    // ZF_LOGI("test nth %c",temp[0]);
    intptr_t n = 0;
    for (n = 0; n < strlen(temp); n++) {
        tensor_index =
            tensor_index + (int)(pow(3, n) + 0.5) * (temp[n] - '0' - 1);
        // ZF_LOGI("The nth %i %i %i, %i, %i, %i %c %f", n, tensor_index,
        // (int)(pow(3, n) + 0.5), temp[n], '0', (temp[n] - '0'), temp[n],
        // pow(3, n));
    }
    return tensor_index;
}

void n_material_tensor_assign_by_index_string(double* tensor,
                                              const char* equal_string,
                                              double value) {
    int sign = -1, tensor_index = 0;
    if (equal_string[0] == '-') {
        equal_string = &equal_string[1];
        sign = -1;
    } else {
        sign = 1;
    }

    tensor_index = n_material_index_string_to_int(equal_string);
    ZF_LOGI("assign %i %s %i %f", sign, equal_string, tensor_index, value);
    // ZF_LOGI("The index %i %p ", tensor_index, tensor);
    tensor[tensor_index] = sign * value;
}

double n_material_tensor_get_by_index_string(double* tensor,
                                             const char* index_string) {
    double out = 0;
    int sign = -1, tensor_index = 0;
    if (index_string[0] == '\0') {
        return 0;
    } else if (index_string[0] == '-') {
        index_string = &index_string[1];
        sign = -1;
    } else if (index_string[0] == '+') {
        index_string = &index_string[1];
        sign = 1;
    } else {
        sign = 1;
    }

    tensor_index = n_material_index_string_to_int(index_string);
    out = sign * tensor[tensor_index];
    return out;
}

double _component_value_get(int n, ComponentValue cv[n], const char* index) {
    int i = 0;
    for (i = 0; i < n; i++) {
        if (strcmp(cv[i].index, index) == 0) {
            return cv[i].value;
        }
    }
    return 0;
}

void n_material_generate_tensor(double* tensor,
                                int unique,
                                NStringArray pg[unique],
                                ComponentValue cv[unique]) {
    double value = 0;
    int i = 0;
    char temp[10] = {'\0'};
    // int found = -1;
    for (i = 0; i < unique; i++) {
        int k = 0;
        int sign = 0;
        sprintf(temp, "%s%s", "-", cv[i].index);
        // strcpy(cv[i].index, index);
        value = cv[i].value;
        // ZF_LOGI("the tensor value and index %f %s", cv[i].value,
        // cv[i].index);
        for (k = 0; k < unique; k++) {
            int j = 0;
            for (j = 0; j < pg[k].length; j++) {
                // ZF_LOGI("The tensor %i %i %i %i %i %i %s %s",
                //         i,
                //         k,
                //         j,
                //         unique,
                //         pg[k].length,
                //         sign,
                //         pg[k].data[j],
                //         cv[i].index);
                if (strcmp(pg[k].data[j], cv[i].index) == 0) {
                    sign = 1;
                    break;
                } else if (strcmp(pg[k].data[j], temp) == 0) {
                    sign = -1;
                    break;
                }
            }
            if (sign != 0) {
                break;
            }
        }

        if (sign != 0) {
            int l = 0;

            for (l = 0; l < pg[k].length; l++) {
                // ZF_LOGI("The material tensor generator %i %i %i %s %f",
                //         i,
                //         k,
                //         l,
                //         pg[k].data[l],
                //         sign * value);
                n_material_tensor_assign_by_index_string(
                    tensor, pg[k].data[l], sign * value);
            }
        } else {
            ZF_LOGE("Problem when creating tensor %s %f", cv[i].index, value);
        }
    }
}

void n_material_generator_one_tensor(double* tensor,
                                     const char* filename,
                                     const char* xpathText) {
    char temp[MAX_STRING] = {'\0'};
    char tensor_name[MAX_STRING] = {'\0'};

    NStringArray tt;
    int rank = 2;
    int sign = 1;
    double value = 0;
    int count = 0;

    char equal_string[10] = {'\0'};
    char index_string[10] = {'\0'};

    sprintf(temp, "%s%s", xpathText, "/rank");
    rank = n_get_xml_element_as_int(filename, temp, "", 2);

    char point_group[10] = "custom";
    sprintf(temp, "%s%s", xpathText, "/pointGroup");
    n_get_xml_element_as_string(point_group, filename, temp, "", "custom");

    sprintf(temp, "%s%s", xpathText, "/name");
    n_get_xml_element_as_string(tensor_name, filename, temp, "", "tensorname");

    sprintf(temp, "%s%s%s", xpathText, "/", tensor_name);
    ZF_LOGI("The name is %s %s",temp,tensor_name);
    if(strcmp(tensor_name,"Ebreak")==0){
        n_material_generator_tensor_general_rank0(tensor, filename, xpathText);
        n_material_tensor_print(tensor, rank, temp);
    }else if (strcmp(tensor_name, "permittivity") == 0 ||
        strcmp(tensor_name, "diffusivity") == 0 ||
        strcmp(tensor_name, "permeability") == 0 ||
        strcmp(tensor_name, "electrical_conductivity") == 0 ||
        strcmp(tensor_name, "thermal_conductivity") == 0) {
                ZF_LOGI("before general tensor rank2");
                ZF_LOGI("before general tensor rank2 another");

        n_material_generator_tensor_rank2(tensor, filename, xpathText);
        n_material_tensor_print(tensor, rank, temp);
    } else if (strcmp(tensor_name, "stiffness") == 0) {
        n_material_generator_tensor_stiffness(tensor, filename, xpathText);
        n_material_tensor_print_stiffness(tensor, temp);
    } else if (strcmp(tensor_name, "piezoelectric") == 0) {
        n_material_generator_tensor_piezoelectric(tensor, filename, xpathText);
        n_material_tensor_print_piezoelectric(tensor, temp);
    } else if (strcmp(tensor_name, "piezomagnetic") == 0) {
        n_material_generator_tensor_piezomagnetic(tensor, filename, xpathText);
        n_material_tensor_print_piezomagnetic(tensor, temp);
    }else{
        ZF_LOGI("******** The tensor is not recongized%s",tensor_name);
    }
}

int n_material_get_tensor_rank(const char* filename,
                               const char* xpathText,
                               const char* tensorname) {
    char temp[MAX_STRING] = {'\0'};
    int tensor_count = 0;
    char tensor_name[MAX_STRING] = {'\0'};

    tensor_count = n_get_xml_element_count(filename, xpathText, "");
    size_t j = 0;
    for (j = 0; j < tensor_count; j++) {
        sprintf(temp, "%s%s%zu%s", xpathText, "[", j + 1, "]/name");
        n_get_xml_element_as_string(
            tensor_name, filename, temp, "", "tensorname");
        // ZF_LOGD("The tensorname %s %s", tensor_name, tensorname);
        if (strcmp(tensor_name, tensorname) == 0) {
            sprintf(temp, "%s%s%zu%s", xpathText, "[", j + 1, "]/rank");
            return n_get_xml_element_as_int(filename, temp, "", 2);
            // *tensor = malloc(sizeof(double[phase_count][(int)pow(3, rank)]));
            // break;
        }
    }
    return 0;
}