#include <nstructuregenerator/structuregenerator.h>
#include <nstructuregenerator/structures.h>

int matrixLabel = 0;

int structure_nx, structure_ny, structure_nz;
int* dat;

// next step needs to add the _Generic function of insert geometry

void n_generate_structure_from_file_f(int* nx,
                                      int* ny,
                                      int* nz,
                                      short** dat,
                                      const char* fileName,
                                      const char* path) {
    n_generate_structure_from_file(
        *nx, *ny, *nz, NPTR2ARR3D(short, *dat, *nx, *ny, *nz), fileName, path);
}

void n_generate_structure_from_file(int nx,
                                    int ny,
                                    int nz,
                                    short dat[nx][ny][nz],
                                    const char* fileName,
                                    const char* path) {
    char geometry[MAX_STRING] = {'\0'};
    // int geometry = 0;
    char xpathText[MAX_STRING] = {'\0'};
    char sourceType[MAX_STRING] = {'\0'};
    char dataType[MAX_STRING] = {'\0'};
    int geometryCount = 0;
    ControlFilePtr cf = n_ControlFile_init(fileName, "input");
    char fileLocation[MAX_STRING] = {'\0'};

    sprintf(xpathText, "%s%s", path, "/sourceType");
    // strcpy(xpathText, "/input/structure/sourceType");
    strcpy(sourceType, "xml");
    n_ControlFile_get_text_by_xpath(sourceType, cf->doc, xpathText, "");
    int volume_count = 0;
    if ((n_string_equal(sourceType, "vti") == 1) ||
        (n_string_equal(sourceType, "dat") == 1)) {
        sprintf(xpathText, "%s%s", path, "/dataType");
        strcpy(dataType, "discrete");
        n_ControlFile_get_text_by_xpath(dataType, cf->doc, xpathText, "");
        sprintf(xpathText, "%s%s", path, "/file");
        n_ControlFile_get_text_by_xpath(fileLocation, cf->doc, xpathText, "");
        ZF_LOGI("The structure file location %s", fileLocation);
        if (n_string_equal(dataType, "continuous") == 1) {
            double* double_dat = calloc(nx * ny * nz, sizeof(double));
            double(*ddat)[nx][ny][nz] =
                &NPTR2ARR3D(double, double_dat, nx, ny, nz);
            if (n_string_equal(sourceType, "vti") == 1) {
                n_vtiFile_3D_double_read(nx, ny, nz, *ddat, fileLocation);
            } else if (n_string_equal(sourceType, "dat") == 1) {
                n_datFile_3D_double_read(nx, ny, nz, *ddat, fileLocation);
            }
            // read key points
            sprintf(xpathText, "%s%s", path, "/keypoints/value");
            int key_count =
                n_ControlFile_get_nodeset_count_by_xpath(cf->doc, xpathText);
            double* keypoints = calloc(key_count, sizeof(double));
            ZF_LOGI("The key count %i", key_count);
            for (int l = 0; l < key_count; l++) {
                sprintf(xpathText,
                        "%s%s%i%s",
                        path,
                        "/keypoints/value[",
                        l + 1,
                        "]");
                keypoints[l] = n_ControlFile_get_double_by_xpath(
                    cf->doc, xpathText, "", 0.5);
            }
            // sort key points
            n_data_1D_double_sort_ascend(
                key_count, NPTR2ARR1D(double, keypoints, key_count));
            // convert double to short
            // ZF_LOGI("After ascend");
            n_data_3D_convert_double_to_short(
                nx,
                ny,
                nz,
                *ddat,
                dat,
                key_count,
                NPTR2ARR1D(double, keypoints, key_count));
            // ZF_LOGI("After convert");

            free(double_dat);
            free(keypoints);
        } else {
            if (n_string_equal(sourceType, "vti") == 1) {
                n_vtiFile_3D_short_read(nx, ny, nz, dat, fileLocation);
            } else if (n_string_equal(sourceType, "dat") == 1) {
                n_datFile_3D_short_read(nx, ny, nz, dat, fileLocation);
            }
        }
    } else if (n_string_equal(sourceType, "dream3d") == 1) {
        sprintf(xpathText, "%s%s", path, "/file");
        n_ControlFile_get_text_by_xpath(fileLocation, cf->doc, xpathText, "");
        n_dream3DFile_3D_short_read(nx, ny, nz, dat, fileLocation);
    } else if (n_string_equal(sourceType, "xml") == 1) {
        sprintf(xpathText, "%s%s", path, "/geometry");
        // strcpy(xpathText, "/input/structure/geometry");

        // ZF_LOGD("c data %p %p",dat, dat[0][0][0][0]);
        geometryCount =
            n_ControlFile_get_nodeset_count_by_xpath(cf->doc, xpathText);
        // sprintf(xpathText,"%s%i%s","/input/structure/matrixLabel");
        // strcpy(xpathText, "/input/structure/matrixLabel");
        sprintf(xpathText, "%s%s", path, "/matrixLabel");

        matrixLabel = n_ControlFile_get_int_by_xpath(cf->doc, xpathText, "", 0);
        n_data_3D_short_assign(nx, ny, nz, dat, matrixLabel);
        // ZF_LOGD("after point update ");
        int tmp = 0;
        int index = 0;
        for (index = 0; index < geometryCount; index++) {
            sprintf(
                xpathText, "%s%s%i%s", path, "/geometry[", index + 1, "]/type");
            n_ControlFile_get_text_by_xpath(geometry, cf->doc, xpathText, "");
            n_string_trim(geometry, "\t\n\v\f\r ");
            printf("Adding a new geometry: %s \n", geometry);
            sprintf(xpathText, "%s%s%i%s", path, "/geometry[", index + 1, "]");
            if (strcmp(geometry, "slab") == 0) {
                tmp = n_generate_NSlab_from_file(
                    nx, ny, nz, dat, fileName, xpathText);
            } else if (strcmp(geometry, "ellipsoid") == 0) {
                tmp = n_generate_NEllipsoid_from_file(
                    nx, ny, nz, dat, fileName, xpathText);
            } else if (strcmp(geometry, "ellipsoid_random") == 0) {
                // ZF_LOGD("Generating the random ellipsoid");
                tmp = n_generate_NEllipsoid_random_from_file(
                    nx, ny, nz, dat, fileName, xpathText);
            } else if (strcmp(geometry, "ellipsoid_random_scale") == 0) {
                // ZF_LOGD("Generating the random ellipsoid");
                tmp = n_generate_NEllipsoid_random_scale_from_file(
                    nx, ny, nz, dat, fileName, xpathText);
            } else if (strcmp(geometry, "ellipsoid_shell") == 0) {
                tmp = n_generate_NEllipsoidShell_from_file(
                    nx, ny, nz, dat, fileName, xpathText);
            } else if (strcmp(geometry, "ellipsoid_shell_random") == 0) {
                // ZF_LOGD("Generating the random ellipsoid");
                tmp = n_generate_NEllipsoidShell_random_from_file(
                    nx, ny, nz, dat, fileName, xpathText);
            } else if (strcmp(geometry, "ellipsoid_shell_random_scale") == 0) {
                // ZF_LOGD("Generating the random ellipsoid");
                tmp = n_generate_NEllipsoidShell_random_scale_from_file(
                    nx, ny, nz, dat, fileName, xpathText);
                // volume_count = volume_count + tmp;
            }
        }
    } else {
        ZF_LOGE("You must choose the source type among xml, vti, and dat");
    }
    if (n_string_equal(sourceType, "dat") == 1) {
        n_datFile_3D_short_write(nx, ny, nz, dat, "microstructure_check.dat");
        n_vtiFile_3D_short_write(nx, ny, nz, dat, "microstructure_check.vti");
    } else {
        n_vtiFile_3D_short_write(nx, ny, nz, dat, "microstructure_check.vti");
    }
    volume_count = n_data_3D_short_not_equal_count(nx, ny, nz, dat, 0);
    n_string_concat(xpathText, 3, "/", MY_STRUCTURE_FILE_ROOT, "/count");
    n_set_xml_element_by_int(volume_count, MY_STRUCTURE_FILE, xpathText, 0);
    // return dat;
}

void n_structure_assign_data_f(int* nx,
                               int* ny,
                               int* nz,
                               int* component,
                               double** dat,
                               short** structure,
                               int* compare,
                               double** assignValue) {
    n_structure_assign_data(*nx,
                            *ny,
                            *nz,
                            *component,
                            NPTR2ARR4D(double, *dat, *nx, *ny, *nz, *component),
                            NPTR2ARR3D(short, *structure, *nx, *ny, *nz),
                            *compare,
                            *assignValue);
}

void n_structure_assign_data(int x,
                             int y,
                             int z,
                             int c,
                             double data[x][y][z][c],
                             short structure[x][y][z],
                             int compare,
                             double assignValue[c]) {
    int i = 0;
    int j = 0;
    int k = 0;
    int l = 0;
    for (i = 0; i < x; i++) {
        for (j = 0; j < y; j++) {
            for (k = 0; k < z; k++) {
                if (structure[i][j][k] == compare) {
                    for (l = 0; l < c; l++) {
                        data[i][j][k][l] = assignValue[l];
                    }
                }
            }
        }
    }
}