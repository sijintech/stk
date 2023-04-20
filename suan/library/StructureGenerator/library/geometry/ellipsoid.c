#include <nstructuregenerator/structures.h>

int NEllipsoid_allowOverlap = 0;    // boolean
int NEllipsoid_accumulateIndex = 0; // boolean
int NEllipsoid_periodic = 1;        // boolean

void NEllipsoid_data_in_int(const char *name, int in) {
  if (strcmp(name, "allowOverlap") == 0) {
    NEllipsoid_allowOverlap = in;
  } else if (strcmp(name, "accumulateIndex") == 0) {
    NEllipsoid_accumulateIndex = in;
  }
}

// Here the rotation angle is for the rotation starting from the simple
// ellipsoid to the general oblique one
//  and the transformation matrix is for rotating the point coordinate from the
//  current system to the ellipsoid system,
// so we use a inverse as the final rotation matrix.
NEllipsoidPtr n_NEllipsoid_init(NPointPtr point, double radiusX, double radiusY,
                              double radiusZ, double rotationX,
                              double rotationY, double rotationZ) {
  NEllipsoidPtr ellipsoid;
  ellipsoid = malloc(sizeof(NEllipsoid));
  memset(ellipsoid, 0, sizeof(NEllipsoid));
  ellipsoid->center = point;
  ellipsoid->radiusX = radiusX;
  ellipsoid->radiusY = radiusY;
  ellipsoid->radiusZ = radiusZ;
  double temp[3][3] = {0};
  temp[0][0] = 1;
  temp[1][1] = 1;
  temp[2][2] = 1;
  n_transformation_matrix_by_tait_bryan(
      temp, rotationX * NDEG2RAD, rotationY * NDEG2RAD, rotationZ * NDEG2RAD);
  n_matrix33_inverse(ellipsoid->rotation, temp);
  // print_matrix33("rotation",temp);

  // double axis[3]={1,0,0};
  // get_transformation_matrix_axis_angle(temp, axis, 45*NDEG2RAD);
  //     print_matrix33("rotation",temp);

  // ZF_LOGD("rotation matrix temp %f %f %f",temp[0][0], temp[1][2],temp[2][2]);
  // ZF_LOGD("rotation angle %f %f %f",rotationX*NDEG2RAD, rotationY*NDEG2RAD,
  // rotationZ*NDEG2RAD); ZF_LOGD("rotation matrix rotation %f %f
  // %f",ellipsoid->rotation[0][0],
  // ellipsoid->rotation[1][2],ellipsoid->rotation[2][2]);
  return ellipsoid;
}

NEllipsoidPtr n_NEllipsoid_init_from_file(const char *fileName,
                                        const char *xpath2geometry) {
  char geometry[MAX_STRING] = {'\0'};
  char xpathText[MAX_STRING] = {'\0'};
  ControlFilePtr cf = n_ControlFile_init(fileName, NULL);
  n_string_join(xpathText, xpath2geometry, "/type", "");
  n_ControlFile_get_text_by_xpath(geometry, cf->doc, xpathText, "");
  n_string_trim(geometry, "\t\n\v\f\r ");
  if (strcmp(geometry, "ellipsoid") != 0) {
    ZF_LOGE("The geometry %s, %s, %s, %s, is not a ellipsoid ", fileName,
            xpath2geometry, xpathText, geometry);
    return NULL;
  } else {
    ZF_LOGI("NEllipsoid");
  }

  double centerX, centerY, centerZ;
  double radiusX, radiusY, radiusZ;
  double rotationX, rotationY, rotationZ;
  n_string_join(xpathText, xpath2geometry, "/centerX", "");
  centerX = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/centerY", "");
  centerY = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/centerZ", "");
  centerZ = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  NPointPtr center = n_NPoint_init(centerX, centerY, centerZ);

  n_string_join(xpathText, xpath2geometry, "/radiusX", "");
  radiusX = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/radiusY", "");
  radiusY = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/radiusZ", "");
  radiusZ = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);

  n_string_join(xpathText, xpath2geometry, "/rotationX", "");
  rotationX = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 0);
  n_string_join(xpathText, xpath2geometry, "/rotationY", "");
  rotationY = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 0);
  n_string_join(xpathText, xpath2geometry, "/rotationZ", "");
  rotationZ = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 0);

  NEllipsoidPtr ellipsoid = n_NEllipsoid_init(center, radiusX, radiusY, radiusZ,
                                            rotationX, rotationY, rotationZ);
  n_ControlFile_free(cf);
  // n_NPoint_free(center);
  return ellipsoid;
}

void n_NEllipsoid_free(NEllipsoidPtr ellipsoid) {
  free(ellipsoid->center);
  free(ellipsoid);
}

double n_NEllipsoid_volume(NEllipsoidPtr ellipsoid) {
  return 4 / 3 * NPI * ellipsoid->radiusX * ellipsoid->radiusY *
         ellipsoid->radiusZ;
}

void n_NEllipsoid_print(NEllipsoidPtr ellipsoid, const char *text) {
  ZF_LOGI("---------- Ellipsoid %s Begin ----------", text);
  ZF_LOGI("| Center  : %6.2f %6.2f %6.2f", ellipsoid->center->x,
          ellipsoid->center->y, ellipsoid->center->z);
  ZF_LOGI("| Radius  : %6.2f %6.2f %6.2f", ellipsoid->radiusX,
          ellipsoid->radiusY, ellipsoid->radiusZ);
  ZF_LOGI("|           %6.2f %6.2f %6.2f", ellipsoid->rotation[0][0],
          ellipsoid->rotation[0][1], ellipsoid->rotation[0][2]);
  ZF_LOGI("| rotation: %6.2f %6.2f %6.2f", ellipsoid->rotation[1][0],
          ellipsoid->rotation[1][1], ellipsoid->rotation[1][2]);
  ZF_LOGI("|           %6.2f %6.2f %6.2f", ellipsoid->rotation[2][0],
          ellipsoid->rotation[2][1], ellipsoid->rotation[2][2]);
  ZF_LOGI("----------- Ellipsoid %s End -----------", text);
}

void n_NEllipsoid_print_xml_by_writer(NEllipsoidPtr ellipsoid,
                                     xmlTextWriterPtr writer,
                                     const char *ellipsoidName) {
  int rc;
  char temp[32];

  rc = xmlTextWriterStartElement(writer, BAD_CAST ellipsoidName);
  rc = xmlTextWriterStartElement(writer, BAD_CAST "type");
  sprintf(temp, "%s", "ellipsoid");
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For type

  rc = xmlTextWriterStartElement(writer, BAD_CAST "volume");
  double volume = n_NEllipsoid_volume(ellipsoid);
  sprintf(temp, "%f", volume);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For volume

  rc = xmlTextWriterStartElement(writer, BAD_CAST "count");
  sprintf(temp, "%i", ellipsoid->count);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For count

  rc = xmlTextWriterStartElement(writer, BAD_CAST "center");
  rc = xmlTextWriterStartElement(writer, BAD_CAST "x");
  sprintf(temp, "%f", ellipsoid->center->x);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For x
  rc = xmlTextWriterStartElement(writer, BAD_CAST "y");
  sprintf(temp, "%f", ellipsoid->center->y);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For y
  rc = xmlTextWriterStartElement(writer, BAD_CAST "z");
  sprintf(temp, "%f", ellipsoid->center->z);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For z
  rc = xmlTextWriterEndElement(writer); // For center

  rc = xmlTextWriterStartElement(writer, BAD_CAST "radius");
  rc = xmlTextWriterStartElement(writer, BAD_CAST "x");
  sprintf(temp, "%f", ellipsoid->radiusX);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For x
  rc = xmlTextWriterStartElement(writer, BAD_CAST "y");
  sprintf(temp, "%f", ellipsoid->radiusY);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For y
  rc = xmlTextWriterStartElement(writer, BAD_CAST "z");
  sprintf(temp, "%f", ellipsoid->radiusZ);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For z
  rc = xmlTextWriterEndElement(writer); // For radius

  rc = xmlTextWriterStartElement(writer, BAD_CAST "rotation");
  rc = xmlTextWriterStartElement(writer, BAD_CAST "r11");
  sprintf(temp, "%f", ellipsoid->rotation[0][0]);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For 11
  rc = xmlTextWriterStartElement(writer, BAD_CAST "r12");
  sprintf(temp, "%f", ellipsoid->rotation[0][1]);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For 12
  rc = xmlTextWriterStartElement(writer, BAD_CAST "r13");
  sprintf(temp, "%f", ellipsoid->rotation[0][2]);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For 13
  rc = xmlTextWriterStartElement(writer, BAD_CAST "r21");
  sprintf(temp, "%f", ellipsoid->rotation[1][0]);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For 21
  rc = xmlTextWriterStartElement(writer, BAD_CAST "r22");
  sprintf(temp, "%f", ellipsoid->rotation[1][1]);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For 22
  rc = xmlTextWriterStartElement(writer, BAD_CAST "r23");
  sprintf(temp, "%f", ellipsoid->rotation[1][2]);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For 23
  rc = xmlTextWriterStartElement(writer, BAD_CAST "r31");
  sprintf(temp, "%f", ellipsoid->rotation[2][0]);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For 31
  rc = xmlTextWriterStartElement(writer, BAD_CAST "r32");
  sprintf(temp, "%f", ellipsoid->rotation[2][1]);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For 32
  rc = xmlTextWriterStartElement(writer, BAD_CAST "r33");
  sprintf(temp, "%f", ellipsoid->rotation[2][2]);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For 33
  rc = xmlTextWriterEndElement(writer); // For rotation

  rc = xmlTextWriterEndElement(writer); // For geometry
}

void n_NEllipsoid_print_xml(NEllipsoidPtr ellipsoid, const char *filename,
                           const char *xpathText, const char *ellipsoidName) {
  //char newxpath[MAX_STRING] = {0};
  // n_string_join(newxpath, xpathText, "ellipsoid", "/");
  xmlTextWriterPtr writer;
  ControlFilePtr cf = n_ControlFile_init(filename, MY_STRUCTURE_FILE_ROOT);
  xmlNodePtr node =
      n_ControlFile_get_nth_nodeset_by_xpath(cf->doc, xpathText, 0);
  writer = xmlNewTextWriterTree(cf->doc, node, 0);

  n_NEllipsoid_print_xml_by_writer(ellipsoid, writer, ellipsoidName);

  xmlFreeTextWriter(writer);

  xmlSaveFileEnc(filename, cf->doc, MY_STRUCTURE_ENCODING);

  n_ControlFile_free(cf);
}

// a periodic appearance of point within the box region
int n_NPoint_within_NEllipsoid_periodic(BoxPtr box, NPointPtr point,
                                      NEllipsoidPtr ellipsoid) {
  int pointInBox = n_NPoint_within_Box(point, box);
  int pointInNEllipsoid = 0;
  if (pointInBox == 0)
    return 0;

  double x = point->x, y = point->y, z = point->z;
  NPointPtr point1 = n_NPoint_init(x, y, z);

  // the original pointß
  pointInNEllipsoid = n_NPoint_within_NEllipsoid(point, ellipsoid);
  if (pointInNEllipsoid == 1)
    return 1;

  // x+ direction
  n_NPoint_update(point1, x + box->xmax - box->xmin + 1, y, z);
  pointInNEllipsoid = n_NPoint_within_NEllipsoid(point1, ellipsoid);
  if (pointInNEllipsoid == 1)
    return 1;

  // x- direction
  n_NPoint_update(point1, x - box->xmax + box->xmin - 1, y, z);
  pointInNEllipsoid = n_NPoint_within_NEllipsoid(point1, ellipsoid);
  if (pointInNEllipsoid == 1) {
    // ZF_LOGD("the x- direction %f %f %f", x, y, z);
    return 1;
  }
  // y+ direction
  n_NPoint_update(point1, x, y + box->ymax - box->ymin + 1, z);
  pointInNEllipsoid = n_NPoint_within_NEllipsoid(point1, ellipsoid);
  if (pointInNEllipsoid == 1)
    return 1;

  // y- direction
  n_NPoint_update(point1, x, y - box->ymax + box->ymin - 1, z);
  pointInNEllipsoid = n_NPoint_within_NEllipsoid(point1, ellipsoid);
  if (pointInNEllipsoid == 1)
    return 1;

  // z+ direction
  n_NPoint_update(point1, x, y, z + box->zmax - box->zmin + 1);
  pointInNEllipsoid = n_NPoint_within_NEllipsoid(point1, ellipsoid);
  if (pointInNEllipsoid == 1)
    return 1;

  // z- direction
  n_NPoint_update(point1, x, y, z - box->zmax + box->zmin - 1);
  pointInNEllipsoid = n_NPoint_within_NEllipsoid(point1, ellipsoid);
  if (pointInNEllipsoid == 1)
    return 1;

  return 0;
}

int n_NPoint_within_NEllipsoid(NPointPtr point, NEllipsoidPtr ellipsoid) {
  double input[3] = {point->x - ellipsoid->center->x,
                     point->y - ellipsoid->center->y,
                     point->z - ellipsoid->center->z},
         output[3] = {0};
  n_matrix33_multiply_vector3(output, ellipsoid->rotation, input);

  double distance = 0;
  distance = pow(output[0], 2) / pow(ellipsoid->radiusX, 2) +
             pow(output[1], 2) / pow(ellipsoid->radiusY, 2) +
             pow(output[2], 2) / pow(ellipsoid->radiusZ, 2);
  if (distance <= 1) {
    // ZF_LOGD("point within %f %f %f %f %f %f
    // %f",distance,output[0],output[1],input[2],ellipsoid->center->x,ellipsoid->center->y,ellipsoid->center->z);
    return 1;
  } else {
    return 0;
  }
}

// Add one ellipsoid to the current phase distribution
int n_NEllipsoid_insert(int nx, int ny, int nz, short dat[nx][ny][nz],
                       NEllipsoidPtr ellipsoid, int label, int matrixLabel) {
  NPointPtr point = n_NPoint_init(0, 0, 0);
  int pointWithin = 0;
  int allow = 1;
  int out = -1;
  int sum = 0;
  //int sum1 = 0;
  size_t i=0;
  size_t j=0;
  size_t k=0;
  if (NEllipsoid_allowOverlap != 1) {

    for (i = 1; i < nx + 1; i++) {
      for (j = 1; j < ny + 1; j++) {
        for (k = 1; k < nz + 1; k++) {
          if (dat[i - 1][j - 1][k - 1] != matrixLabel) {
            n_NPoint_update(point, (double)i, (double)j, (double)k);
            if (NEllipsoid_periodic == 0) {
              pointWithin = n_NPoint_within_NEllipsoid(point, ellipsoid);
            } else {
              BoxPtr box =
                  n_Box_init(1, (double)nx, 1, (double)ny, 1, (double)nz);
              pointWithin =
                  n_NPoint_within_NEllipsoid_periodic(box, point, ellipsoid);
            }
            sum = pointWithin + sum;
            // ZF_LOGD("something notx allowed %i %i %i %i
            // %i",sum,pointWithin,i,j,k);
            if (pointWithin == 1) {
              allow = 0;
              pointWithin = 0;
              // goto notallow;
            }
          }
        }
      }
    }
  }
  if (allow == 1) {
    out = 0;

    for (i = 1; i < nx + 1; i++) {
      for (j = 1; j < ny + 1; j++) {
        for (k = 1; k < nz + 1; k++) {
          n_NPoint_update(point, (double)i, (double)j, (double)k);
          if (NEllipsoid_periodic == 0) {
            pointWithin = n_NPoint_within_NEllipsoid(point, ellipsoid);
          } else {
            BoxPtr box =
                n_Box_init(1, (double)nx, 1, (double)ny, 1, (double)nz);
            pointWithin =
                n_NPoint_within_NEllipsoid_periodic(box, point, ellipsoid);
          }
          if (pointWithin == 1) {
            dat[i - 1][j - 1][k - 1] = (short)label;
            out = out + 1;
            // ZF_LOGD("point founded %i %i %i",i,j,k);
          }
          // sum = pointWithin +sum;
          //   sum1 = dat[i - 1][j - 1][k - 1] + sum1;
        }
      }
    }
    // if (NEllipsoid_accumulateIndex == 1) {
    //   out = label + 1;
    // } else {
    //   out = label;
    // }
    ellipsoid->count = out;
  }

  // notallow:
  // ZF_LOGD("allow not allow %i %i %i %i ",allow,sum,sum1,out);
  // ZF_LOGD("allow not allow %f %f %f %f %f
  // %f",ellipsoid->center->x,ellipsoid->center->y,ellipsoid->center->z,ellipsoid->radiusX,ellipsoid->radiusY,ellipsoid->radiusZ);

  n_NPoint_free(point);

  return out; // -1 means unsuccessful insert, otherwise return the next label
}

int n_generate_NEllipsoid_from_file(int nx, int ny, int nz, short dat[nx][ny][nz],
                                   const char *fileName,
                                   const char *xpath2geometry) {
  NEllipsoidPtr ellipsoid = n_NEllipsoid_init_from_file(fileName, xpath2geometry);
  int label, flag, matrixLabel, matrixLabelGlobal;
  char xpathText[MAX_STRING] = {'\0'};
  n_string_join(xpathText, xpath2geometry, "/label", "");
  ControlFilePtr cf = n_ControlFile_init(fileName, NULL);
  label = n_ControlFile_get_int_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/matrixLabel", "");
  matrixLabelGlobal = n_ControlFile_get_int_by_xpath(cf->doc, "/input/structure/matrixLabel", "", 0);
  matrixLabel = n_ControlFile_get_int_by_xpath(cf->doc, xpathText, "", matrixLabelGlobal);
  flag = n_NEllipsoid_insert(nx, ny, nz, dat, ellipsoid, label, matrixLabel);
  n_string_concat(xpathText, 2, "/", MY_STRUCTURE_FILE_ROOT);
  if (flag == -1) {
    ZF_LOGI("missed an ellipsoid");
  } else {
    if (NEllipsoid_accumulateIndex == 1) {
      label = label + 1;
    }
    n_NEllipsoid_print(ellipsoid, "");
    n_NEllipsoid_print_xml(ellipsoid, MY_STRUCTURE_FILE, xpathText, "geometry");
  }

  n_NEllipsoid_free(ellipsoid);
  n_ControlFile_free(cf);
  return flag;
}