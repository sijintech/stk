#include <nmaterialgenerator/material.h>

// nonzero, unique, independent

//  1(C1), \bar{1}(S2)
const PointGroup stiffness_triclinic = {
    81,
    21,
    21,
    {{1, {"1111"}},
     {1, {"2222"}},
     {1, {"3333"}},
     {2, {"1122", "2211"}},
     {2, {"1133", "3311"}},
     {2, {"2233", "3322"}},
     {4, {"1123", "1132", "2311", "3211"}},
     {4, {"1113", "1131", "1311", "3111"}},
     {4, {"1112", "1121", "1211", "2111"}},
     {4, {"2223", "2232", "2322", "3222"}},
     {4, {"2213", "2231", "1322", "3122"}},
     {4, {"2212", "2221", "1222", "2122"}},
     {4, {"3323", "3332", "2333", "3233"}},
     {4, {"3313", "3331", "1333", "3133"}},
     {4, {"3312", "3321", "1233", "2133"}},
     {4, {"2323", "2332", "3223", "3232"}},
     {4, {"1313", "1331", "3113", "3131"}},
     {4, {"1212", "1221", "2112", "2121"}},
     {8, {"2313", "2331", "3213", "3231", "1323", "3123", "1332", "3132"}},
     {8, {"2312", "2321", "3212", "3221", "1223", "2123", "1232", "2132"}},
     {8, {"1213", "1231", "2113", "2131", "1312", "3112", "1321", "3121"}}}};

// 2(C2), m(C1h, C1v, Cs), 2/m(C2h)
const PointGroup stiffness_monoclinic = {
    41,
    13,
    13,
    {{1, {"1111"}},
     {1, {"2222"}},
     {1, {"3333"}},
     {2, {"1122", "2211"}},
     {2, {"1133", "3311"}},
     {2, {"2233", "3322"}},
     {4, {"1113", "1131", "1311", "3111"}},
     {4, {"2213", "2231", "1322", "3122"}},
     {4, {"3313", "3331", "1333", "3133"}},
     {4, {"2323", "2332", "3223", "3232"}},
     {4, {"1313", "1331", "3113", "3131"}},
     {4, {"1212", "1221", "2112", "2121"}},
     {8, {"2312", "2321", "3212", "3221", "1223", "2123", "1232", "2132"}}}};

// 222(D2), mm2(C2v), mmm(D2h)
const PointGroup stiffness_orthorhombic = {
    21,
    9,
    9,
    {{1, {"1111"}},
     {1, {"2222"}},
     {1, {"3333"}},
     {2, {"1122", "2211"}},
     {2, {"1133", "3311"}},
     {2, {"2233", "3322"}},
     {4, {"2323", "2332", "3223", "3232"}},
     {4, {"1313", "1331", "3113", "3131"}},
     {4, {"1212", "1221", "2112", "2121"}}}};

//  4(C4), \bar{4}(S4), 4/m(C4h)
const PointGroup stiffness_tetragonal_1 = {
    29,
    7,
    7,
    {{2, {"1111", "2222"}},
     {1, {"3333"}},
     {2, {"1122", "2211"}},
     {4, {"1133", "3311", "2233", "3322"}},
     {8, {"2323", "2332", "3223", "3232", "1313", "1331", "3113", "3131"}},
     {4, {"1212", "1221", "2112", "2121"}},
     {8,
      {"1112", "1121", "1211", "2111", "-2212", "-2221", "-1222", "-2122"}}}};

//  422(D4), 4mm(C4v), \bar{4}2m(D2d), 4/mmm(D4h)
const PointGroup stiffness_tetragonal_2 = {
    21,
    6,
    6,
    {{2, {"1111", "2222"}},
     {1, {"3333"}},
     {2, {"1122", "2211"}},
     {4, {"1133", "3311", "2233", "3322"}},
     {8, {"2323", "2332", "3223", "3232", "1313", "1331", "3113", "3131"}},
     {4, {"1212", "1221", "2112", "2121"}}}};

// 3(C3), \bar{3}(S6, C3i)
const PointGroup stiffness_trigonal_1 = {
    53,
    8,
    7,
    {{2, {"1111", "2222"}},
     {1, {"3333"}},
     {2, {"1122", "2211"}},
     {4, {"1133", "3311", "2233", "3322"}},
     {8, {"2323", "2332", "3223", "3232", "1313", "1331", "3113", "3131"}},
     {4, {"1212", "1221", "2112", "2121"}},
     {16,
      {"1123",
       "1132",
       "2311",
       "3211",
       "-2223",
       "-2232",
       "-2322",
       "-3222",
       "1312",
       "1321",
       "3112",
       "3121",
       "1213",
       "2113",
       "1231",
       "2131"}},
     {16,
      {"-1113",
       "-1131",
       "-1311",
       "-3111",
       "2213",
       "2231",
       "1322",
       "3122",
       "2312",
       "2321",
       "3212",
       "3221",
       "1223",
       "2123",
       "1232",
       "2132"}}}};

//   32(D3), 3m(C3v), \bar{3} m(D3d)
const PointGroup stiffness_trigonal_2 = {
    37,
    7,
    6,
    {{2, {"1111", "2222"}},
     {1, {"3333"}},
     {2, {"1122", "2211"}},
     {4, {"1133", "3311", "2233", "3322"}},
     {8, {"2323", "2332", "3223", "3232", "1313", "1331", "3113", "3131"}},
     {4, {"1212", "1221", "2112", "2121"}},
     {16,
      {"1123",
       "1132",
       "2311",
       "3211",
       "-2223",
       "-2232",
       "-2322",
       "-3222",
       "1312",
       "1321",
       "3112",
       "3121",
       "1213",
       "2113",
       "1231",
       "2131"}}}};

//    6(C6), \bar{6}(C3h), 6/m(C6h), 622(D6), 6mm(C6v), \bar{6}m2(D3h),
//    6/mmm(D6h)
// inf, infm, inf/m, inf2,inf/mm
const PointGroup stiffness_hexagonal = {
    21,
    6,
    5,
    {{2, {"1111", "2222"}},
     {1, {"3333"}},
     {2, {"1122", "2211"}},
     {4, {"1133", "3311", "2233", "3322"}},
     {8, {"2323", "2332", "3223", "3232", "1313", "1331", "3113", "3131"}},
     {4, {"1212", "1221", "2112", "2121"}}}};

//  23(T), m\bar{3}(Th), 432(O), \bar{4}3m(Td), m\bar{3}m(Oh)
const PointGroup stiffness_cubic = {
    21,
    3,
    3,
    {{3, {"1111", "2222", "3333"}},
     {6, {"1122", "2211", "1133", "3311", "2233", "3322"}},
     {12,
      {"2323",
       "2332",
       "3223",
       "3232",
       "1313",
       "1331",
       "3113",
       "3131",
       "1212",
       "1221",
       "2112",
       "2121"}}}};

//  infinf, infinfm
const PointGroup stiffness_isotropic = {
    21,
    3,
    2,
    {{3, {"1111", "2222", "3333"}},
     {6, {"1122", "2211", "1133", "3311", "2233", "3322"}},
     {12,
      {"2323",
       "2332",
       "3223",
       "3232",
       "1313",
       "1331",
       "3113",
       "3131",
       "1212",
       "1221",
       "2112",
       "2121"}}}};

const int voigt_index[6] = {11, 22, 33, 23, 13, 12};

PointGroup _stiffness_get_PointGroup(const char* point_group) {
    if (strcmp(point_group, "triclinic") == 0) {
        return stiffness_triclinic;
    } else if (strcmp(point_group, "monoclinic") == 0) {
        return stiffness_monoclinic;
    } else if (strcmp(point_group, "orthorhombic") == 0) {
        return stiffness_orthorhombic;
    } else if (strcmp(point_group, "tetragonal1") == 0) {
        return stiffness_tetragonal_1;
    } else if (strcmp(point_group, "tetragonal2") == 0) {
        return stiffness_tetragonal_2;
    } else if (strcmp(point_group, "trigonal1") == 0) {
        return stiffness_trigonal_1;
    } else if (strcmp(point_group, "trigonal2") == 0) {
        return stiffness_trigonal_1;
    } else if (strcmp(point_group, "hexagonal") == 0) {
        return stiffness_hexagonal;
    } else if (strcmp(point_group, "cubic") == 0) {
        return stiffness_cubic;
    } else if (strcmp(point_group, "isotropic") == 0 ||
               strcmp(point_group, "engineer") == 0) {
        return stiffness_isotropic;
    }
    return stiffness_isotropic;
}

void _stiffness_voigt_to_tensor(char* index) {
    char index_string_hold[10] = {'\0'};

    if (strlen(index) == 2) {
        // needs to convert voigt to tensor
        strcpy(index_string_hold, index);

        // ZF_LOGI("overall index %i %s %s",
        //         strlen(index_string),
        //         index_string,
        //         index_string_hold);

        sprintf(index,
                "%i%i",
                voigt_index[index_string_hold[0] - '1'],
                voigt_index[index_string_hold[1] - '1']);
        // sprintf(temp_string, "test%i", 1);
        // ZF_LOGI("voigt index %s", index_string);
    }
}

void n_material_generator_tensor_stiffness(double* tensor,
                                           const char* filename,
                                           const char* xpathText) {
    // custom
    // point group
    // isotropic as default
    char temp[MAX_STRING] = {'\0'};
    int gpindex = 4;
    int k = 0;
    double value = 0;
    char point_group[10] = "cubic\0";
    sprintf(temp, "%s%s", xpathText, "/pointGroup");
    n_get_xml_element_as_string(point_group, filename, temp, "", "isotropic");

    PointGroup pg = stiffness_isotropic;
    ComponentValue* cv;
    pg = _stiffness_get_PointGroup(point_group);
    cv = calloc(pg.unique, sizeof(ComponentValue));
    char index_string[10] = {'\0'};

    // set independent component
    int component_count = 0;
    sprintf(temp, "%s%s", xpathText, "/component");
    component_count = n_get_xml_element_count(filename, temp, "");

    // ZF_LOGI("stiffness tensor %i, %i", component_count, pg.independent);

    if (component_count != pg.independent) {
        ZF_LOGE("The number of component is not suitable for the symmetry you "
                "choose!");
    } else {

        for (k = 0; k < component_count; k++) {
            sprintf(
                temp, "%s%s%i%s", xpathText, "/component[", k + 1, "]/value");
            value = n_get_xml_element_as_double(filename, temp, "", 0);

            sprintf(temp,
                    "%s%s%i%s",
                    xpathText,
                    "/component[",
                    k + 1,
                    "]/index[1]");
            n_get_xml_element_as_string(
                index_string, filename, temp, "", "index");
            // ZF_LOGI("overall index %i %s %i %f",
            //         k,
            //         index_string,
            //         strlen(index_string),
            //         value);

            _stiffness_voigt_to_tensor(index_string);

            cv[k].value = value;
            strcpy(cv[k].index, index_string);
            index_string[0] = '\0';
        }
    }

    // set dependent component
    // ZF_LOGI("the unique stiffness %i %s", pg.unique, point_group);
    if (strcmp(point_group, "trigonal1") == 0 ||
        strcmp(point_group, "trigonal2") == 0 ||
        strcmp(point_group, "hexagonal") == 0 ||
        strcmp(point_group, "isotropic") == 0) {
        value = 0.5 * (_component_value_get(pg.unique, cv, "1111") -
                       _component_value_get(pg.unique, cv, "1122"));
        cv[pg.unique - 1].value = value;
        strcpy(cv[pg.unique - 1].index, "1212");
        // ZF_LOGI("the unique stiffness insdie %s %f",
        //         cv[pg.unique - 1].index,
        //         value);
    } else if (strcmp(point_group, "engineer") == 0) {
        double young = _component_value_get(pg.unique, cv, "young");
        double poisson = _component_value_get(pg.unique, cv, "poisson");
        value = young * (1 - poisson) / ((1 + poisson) * (1 - 2 * poisson));
        // ZF_LOGI("The value %f %f %f", young, poisson, value);
        cv[0].value = value;
        strcpy(cv[0].index, "1111");

        value = young * poisson / ((1 + poisson) * (1 - 2 * poisson));
        cv[1].value = value;
        strcpy(cv[1].index, "1122");

        value = young / (1 + poisson);
        cv[2].value = value;
        strcpy(cv[2].index, "1212");
    }

    n_material_generate_tensor(tensor, pg.unique, pg.relation, cv);
    free(cv);
}

void n_material_tensor_print_stiffness(double* tensor, const char* name) {
    int i = 0;
    ZF_LOGI("---------Begin stiffness tensor in Voigt notation %s-------------",
            name);
    int row[6] = {0, 36, 72, 45, 18, 9};
    for (i = 0; i < 6; i++) {
        ZF_LOGI("%i1=%10.3le %i2=%10.3le %i3=%10.3le %i4=%10.3le %i5=%10.3le "
                "%i6=%10.3le",
                i + 1,
                tensor[row[i]],
                i + 1,
                tensor[row[i] + 3 * 1 + 1],
                i + 1,
                tensor[row[i] + 3 * 2 + 2],
                i + 1,
                tensor[row[i] + 3 * 1 + 2],
                i + 1,
                tensor[row[i] + 3 * 0 + 2],
                i + 1,
                tensor[row[i] + 3 * 0 + 1]);
    }
    ZF_LOGI("--------- End stiffness tensor in Voigt notation %s -------------",
            name);
}

void n_material_tensor_print_file_stiffness(const char* name, double* tensor) {
    FILE* fp;
    // char temp[512] = {'\0'};
    // char temp6[1024] = {'\0'};
    int row[6] = {0, 36, 72, 45, 18, 9};

    fp = fopen(name, "w");
    fprintf(fp, "Index,1,2,3,4,5,6\n");
    int i = 0;
    for (i = 0; i < 6; i++) {
        fprintf(fp,
                "%i,%10.3le,%10.3le,%10.3le,%10.3le,%10.3le,%10.3le\n",
                i + 1,
                tensor[row[i]],
                tensor[row[i] + 3 * 1 + 1],
                tensor[row[i] + 3 * 2 + 2],
                tensor[row[i] + 3 * 1 + 2],
                tensor[row[i] + 3 * 0 + 2],
                tensor[row[i] + 3 * 0 + 1]);
    }
    fclose(fp);
}