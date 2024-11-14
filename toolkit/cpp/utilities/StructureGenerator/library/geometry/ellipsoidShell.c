#include <nstructuregenerator/structures.h>

int NEllipsoidShell_allowOverlap = 0;    // boolean
int NEllipsoidShell_accumulateIndex = 0; // boolean
int NEllipsoidShell_periodic = 1;        // boolean

void NEllipsoidShell_data_in_int(const char *name, int in) {
  if (strcmp(name, "allowOverlap") == 0) {
    NEllipsoidShell_allowOverlap = in;
  } else if (strcmp(name, "accumulateIndex") == 0) {
    NEllipsoidShell_accumulateIndex = in;
  }
}

// Here the rotation angle is for the rotation starting from the simple
// ellipsoid to the general oblique one
//  and the transformation matrix is for rotating the point coordinate from the
//  current system to the ellipsoid system,
// so we use a inverse as the final rotation matrix.
NEllipsoidShellPtr n_NEllipsoidShell_init(NEllipsoidPtr outer,
                                        NEllipsoidPtr inner) {
  NEllipsoidShellPtr ellipsoidShell;
  ellipsoidShell = malloc(sizeof(NEllipsoidShell));
  memset(ellipsoidShell, 0, sizeof(NEllipsoidShell));
  ellipsoidShell->outer = outer;
  ellipsoidShell->inner = inner;
  return ellipsoidShell;
}

NEllipsoidShellPtr n_NEllipsoidShell_init_from_file(const char *fileName,
                                                  const char *xpath2geometry) {
  char geometry[MAX_STRING] = {'\0'};
  char xpathText[MAX_STRING] = {'\0'};
  ControlFilePtr cf = n_ControlFile_init(fileName, NULL);
  n_string_join(xpathText, xpath2geometry, "/type", "");
  n_ControlFile_get_text_by_xpath(geometry, cf->doc, xpathText, "");
  n_string_trim(geometry, "\t\n\v\f\r ");
  if (strcmp(geometry, "ellipsoid_shell") != 0) {
    ZF_LOGE("The geometry %s, %s, %s, %s, is not a ellipsoid shell ", fileName,
            xpath2geometry, xpathText, geometry);
    return NULL;
  } else {
    ZF_LOGI("NEllipsoid Shell");
  }

  double centerXOuter, centerYOuter, centerZOuter;
  double centerXInner, centerYInner, centerZInner;
  double radiusXOuter, radiusYOuter, radiusZOuter;
  double radiusXInner, radiusYInner, radiusZInner;
  double rotationXOuter, rotationYOuter, rotationZOuter;
  double rotationXInner, rotationYInner, rotationZInner;
  n_string_join(xpathText, xpath2geometry, "/centerXOuter", "");
  centerXOuter = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/centerXInner", "");
  centerXInner = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/centerYOuter", "");
  centerYOuter = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/centerYInner", "");
  centerYInner = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/centerZOuter", "");
  centerZOuter = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/centerZInner", "");
  centerZInner = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);

  n_string_join(xpathText, xpath2geometry, "/radiusXOuter", "");
  radiusXOuter = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/radiusXInner", "");
  radiusXInner = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/radiusYOuter", "");
  radiusYOuter = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/radiusYInner", "");
  radiusYInner = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/radiusZOuter", "");
  radiusZOuter = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/radiusZInner", "");
  radiusZInner = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);

  n_string_join(xpathText, xpath2geometry, "/rotationXOuter", "");
  rotationXOuter = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 0);
  n_string_join(xpathText, xpath2geometry, "/rotationXInner", "");
  rotationXInner = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 0);
  n_string_join(xpathText, xpath2geometry, "/rotationYOuter", "");
  rotationYOuter = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 0);
  n_string_join(xpathText, xpath2geometry, "/rotationYInner", "");
  rotationYInner = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 0);
  n_string_join(xpathText, xpath2geometry, "/rotationZOuter", "");
  rotationZOuter = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 0);
  n_string_join(xpathText, xpath2geometry, "/rotationZInner", "");
  rotationZInner = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 0);

  NPointPtr centerOuter = n_NPoint_init(centerXOuter, centerYOuter, centerZOuter);
  NPointPtr centerInner = n_NPoint_init(centerXInner, centerYInner, centerZInner);

  NEllipsoidPtr ellipsoidOuter =
      n_NEllipsoid_init(centerOuter, radiusXOuter, radiusYOuter, radiusZOuter,
                       rotationXOuter, rotationYOuter, rotationZOuter);
  NEllipsoidPtr ellipsoidInner =
      n_NEllipsoid_init(centerInner, radiusXInner, radiusYInner, radiusZInner,
                       rotationXInner, rotationYInner, rotationZInner);
  NEllipsoidShellPtr ellipsoidShell =
      n_NEllipsoidShell_init(ellipsoidOuter, ellipsoidInner);
  // n_NPoint_free(center);
  return ellipsoidShell;
}

void n_NEllipsoidShell_free(NEllipsoidShellPtr ellipsoidShell) {
  n_NEllipsoid_free(ellipsoidShell->outer);
  n_NEllipsoid_free(ellipsoidShell->inner);
  free(ellipsoidShell);
}

double n_NEllipsoidShell_volume(NEllipsoidShellPtr ellipsoidShell) {
  double outerV = n_NEllipsoid_volume(ellipsoidShell->outer);
  double innerV = n_NEllipsoid_volume(ellipsoidShell->inner);
  return outerV - innerV;
}

void n_NEllipsoidShell_print(NEllipsoidShellPtr ellipsoidShell,
                            const char *text) {
  ZF_LOGI("---------- NEllipsoid Shell %s Begin ----------", text);
  n_NEllipsoid_print(ellipsoidShell->outer, "outer");
  n_NEllipsoid_print(ellipsoidShell->inner, "inner");
  ZF_LOGI("---------- NEllipsoid Shell %s End ----------", text);
}

void n_NEllipsoidShell_print_xml_by_writer(NEllipsoidShellPtr ellipsoidShell,
                                          xmlTextWriterPtr writer,
                                          const char *ellipsoidName) {
  int rc;
  char temp[32];
  rc = xmlTextWriterStartElement(writer, BAD_CAST ellipsoidName);
  rc = xmlTextWriterStartElement(writer, BAD_CAST "type");
  sprintf(temp, "%s", "ellipsoid_shell");
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For type

  rc = xmlTextWriterStartElement(writer, BAD_CAST "volume");
  double volume = n_NEllipsoidShell_volume(ellipsoidShell);
  sprintf(temp, "%f", volume);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For volume

  rc = xmlTextWriterStartElement(writer, BAD_CAST "count");
  sprintf(temp, "%i",
          ellipsoidShell->outer->count - ellipsoidShell->inner->count);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For count

  n_NEllipsoid_print_xml_by_writer(ellipsoidShell->outer, writer, "outer");
  n_NEllipsoid_print_xml_by_writer(ellipsoidShell->inner, writer, "inner");

  rc = xmlTextWriterEndElement(writer); // For geometry
}

void n_NEllipsoidShell_print_xml(NEllipsoidShellPtr ellipsoidShell,
                                const char *filename, const char *xpathText,
                                const char *ellipsoidShellName) {
  // char newxpath[MAX_STRING] = {0};
  // n_string_join(newxpath, xpathText, "ellipsoid", "/");
  xmlTextWriterPtr writer;
  ControlFilePtr cf = n_ControlFile_init(filename, MY_STRUCTURE_FILE_ROOT);
  xmlNodePtr node =
      n_ControlFile_get_nth_nodeset_by_xpath(cf->doc, xpathText, 0);
  writer = xmlNewTextWriterTree(cf->doc, node, 0);

  n_NEllipsoidShell_print_xml_by_writer(ellipsoidShell, writer,
                                       ellipsoidShellName);

  xmlFreeTextWriter(writer);

  xmlSaveFileEnc(filename, cf->doc, MY_STRUCTURE_ENCODING);

  n_ControlFile_free(cf);
}

// a periodic appearance of point within the box region
int n_NPoint_within_NEllipsoidShell_periodic(BoxPtr box, NPointPtr point,
                                           NEllipsoidShellPtr ellipsoidShell) {
  int pointInBox = n_NPoint_within_Box(point, box);
  int pointInNEllipsoidShell = 0;
  if (pointInBox == 0)
    return 0;

  double x = point->x, y = point->y, z = point->z;
  NPointPtr point1 = n_NPoint_init(x, y, z);

  // the original point
  pointInNEllipsoidShell = n_NPoint_within_NEllipsoidShell(point, ellipsoidShell);
  if (pointInNEllipsoidShell > 0)
    return pointInNEllipsoidShell;

  // x+ direction
  n_NPoint_update(point1, x + box->xmax - box->xmin + 1, y, z);
  pointInNEllipsoidShell = n_NPoint_within_NEllipsoidShell(point1, ellipsoidShell);
  if (pointInNEllipsoidShell > 0)
    return pointInNEllipsoidShell;

  // x- direction
  n_NPoint_update(point1, x - box->xmax + box->xmin - 1, y, z);
  pointInNEllipsoidShell = n_NPoint_within_NEllipsoidShell(point1, ellipsoidShell);
  if (pointInNEllipsoidShell > 0) {
    // ZF_LOGD("the x- direction %f %f %f", x, y, z);
    return pointInNEllipsoidShell;
  }
  // y+ direction
  n_NPoint_update(point1, x, y + box->ymax - box->ymin + 1, z);
  pointInNEllipsoidShell = n_NPoint_within_NEllipsoidShell(point1, ellipsoidShell);
  if (pointInNEllipsoidShell > 0)
    return pointInNEllipsoidShell;

  // y- direction
  n_NPoint_update(point1, x, y - box->ymax + box->ymin - 1, z);
  pointInNEllipsoidShell = n_NPoint_within_NEllipsoidShell(point1, ellipsoidShell);
  if (pointInNEllipsoidShell > 0)
    return pointInNEllipsoidShell;

  // z+ direction
  n_NPoint_update(point1, x, y, z + box->zmax - box->zmin + 1);
  pointInNEllipsoidShell = n_NPoint_within_NEllipsoidShell(point1, ellipsoidShell);
  if (pointInNEllipsoidShell > 0)
    return pointInNEllipsoidShell;

  // z- direction
  n_NPoint_update(point1, x, y, z - box->zmax + box->zmin - 1);
  pointInNEllipsoidShell = n_NPoint_within_NEllipsoidShell(point1, ellipsoidShell);
  if (pointInNEllipsoidShell == 1)
    return pointInNEllipsoidShell;

  return 0;
}

int n_NPoint_within_NEllipsoidShell(NPointPtr point,
                                  NEllipsoidShellPtr ellipsoidShell) {
  int outer = n_NPoint_within_NEllipsoid(point, ellipsoidShell->outer);
  int inner = n_NPoint_within_NEllipsoid(point, ellipsoidShell->inner);
  if (inner == 1 && outer == 1) {
    // ZF_LOGD("point within %f %f %f %f %f %f
    // %f",distance,output[0],output[1],input[2],ellipsoid->center->x,ellipsoid->center->y,ellipsoid->center->z);
    return 2;
  } else if (inner == 0 && outer == 1) {
    return 1;
  } else if (inner == 0 && outer == 0) {
    return 0;
  } else {
    ZF_LOGE("wierd point and ellipsoid shell relationship. NPoint: %f %f %f. "
            "Relationship: %i %i",
            point->x, point->y, point->z, inner, outer);
    n_NEllipsoidShell_print(ellipsoidShell, "");
    return -1;
  }
}

// Add one ellipsoid to the current phase distribution
int n_NEllipsoidShell_insert(int nx, int ny, int nz, short dat[nx][ny][nz],
                            NEllipsoidShellPtr ellipsoidShell, int label,
                            int innerLabel, int matrixLabel) {
  NPointPtr point = n_NPoint_init(0, 0, 0);
  int pointWithin = 0;
  int allow = 1;
  int out = -1;
  // int sum = 0, sum1 = 0;
  size_t i=0;
  size_t j=0;
  size_t k=0;
  if (NEllipsoidShell_allowOverlap != 1) {
    for (i = 1; i < nx + 1; i++) {
      for (j = 1; j < ny + 1; j++) {
        for (k = 1; k < nz + 1; k++) {
          if (dat[i - 1][j - 1][k - 1] != matrixLabel) {
            n_NPoint_update(point, (double)i, (double)j, (double)k);
            if (NEllipsoidShell_periodic == 0) {
              pointWithin =
                  n_NPoint_within_NEllipsoidShell(point, ellipsoidShell);
            } else {
              BoxPtr box =
                  n_Box_init(1, (double)nx, 1, (double)ny, 1, (double)nz);
              pointWithin = n_NPoint_within_NEllipsoidShell_periodic(
                  box, point, ellipsoidShell);
            }
            // sum = pointWithin +sum;
            // ZF_LOGD("something notx allowed %i %i %i %i
            // %i",sum,pointWithin,i,j,k);
            if (pointWithin > 0) {
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
          if (NEllipsoidShell_periodic == 0) {
            pointWithin = n_NPoint_within_NEllipsoidShell(point, ellipsoidShell);
          } else {
            BoxPtr box =
                n_Box_init(1, (double)nx, 1, (double)ny, 1, (double)nz);
            pointWithin = n_NPoint_within_NEllipsoidShell_periodic(
                box, point, ellipsoidShell);
          }
          if (pointWithin == 1) {
            dat[i - 1][j - 1][k - 1] = (short)label;
            out = out + 1;
            // ZF_LOGD("point founded %i %i %i",i,j,k);
          } else if (pointWithin == 2) {
            dat[i - 1][j - 1][k - 1] = (short)innerLabel;
          }
          // sum = pointWithin +sum;
          // sum1 = dat[i-1][j-1][k-1] +sum1;
        }
      }
    }
    // if (NEllipsoidShell_accumulateIndex == 1) {
    //   out = label + 1;
    // } else {
    //   out = label;
    // }
    ellipsoidShell->count = out;
  }

  // notallow:
  // ZF_LOGD("allow not allow %i %i %i %i ",allow,sum,sum1,out);
  // ZF_LOGD("allow not allow %f %f %f %f %f
  // %f",ellipsoid->center->x,ellipsoid->center->y,ellipsoid->center->z,ellipsoid->radiusX,ellipsoid->radiusY,ellipsoid->radiusZ);

  n_NPoint_free(point);

  return out; // -1 means unsuccessful insert, otherwise return the next label
}

int n_generate_NEllipsoidShell_from_file(int nx, int ny, int nz,
                                        short dat[nx][ny][nz],
                                        const char *fileName,
                                        const char *xpath2geometry) {
  NEllipsoidShellPtr ellipsoidShell =
      n_NEllipsoidShell_init_from_file(fileName, xpath2geometry);
  int label, innerLabel, matrixLabel, matrixLabelGlobal;
  char xpathText[MAX_STRING] = {'\0'};
  n_string_join(xpathText, xpath2geometry, "/label", "");
  ControlFilePtr cf = n_ControlFile_init(fileName, NULL);
  label = n_ControlFile_get_int_by_xpath(cf->doc, xpathText, "", 1);

  n_string_join(xpathText, xpath2geometry, "/labelInner", "");
  innerLabel = n_ControlFile_get_int_by_xpath(cf->doc, xpathText, "", 1);

  n_string_join(xpathText, xpath2geometry, "/matrixLabel", "");
  matrixLabelGlobal = n_ControlFile_get_int_by_xpath(cf->doc, "/input/structure/matrixLabel", "", 0);
  matrixLabel = n_ControlFile_get_int_by_xpath(cf->doc, xpathText, "", matrixLabelGlobal);

  int flag = n_NEllipsoidShell_insert(nx, ny, nz, dat, ellipsoidShell, label,
                                     innerLabel, matrixLabel);
  n_string_concat(xpathText, 2, "/", MY_STRUCTURE_FILE_ROOT);

  if (flag == -1) {
    ZF_LOGI("missed an ellipsoid shell");
  } else {
    if (NEllipsoidShell_accumulateIndex == 1) {
      label = label + 1;
    }
    n_NEllipsoidShell_print(ellipsoidShell, "");
    n_NEllipsoidShell_print_xml(ellipsoidShell, MY_STRUCTURE_FILE, xpathText,
                               "geometry");
  }

  n_NEllipsoidShell_free(ellipsoidShell);
  n_ControlFile_free(cf);
  return flag;
}