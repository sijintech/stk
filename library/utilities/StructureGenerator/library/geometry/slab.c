#include <nstructuregenerator/structures.h>
#include <zf_log.h>

int NSlab_allowOverlap = 0; // boolean
int NSlab_matrixLabel = 0;
int NSlab_accumulateIndex = 0;

void n_NSlab_int_data_set(const char *name, int in) {
  if (strcmp(name, "allowOverlap") == 0) {
    NSlab_allowOverlap = in;
  } else if (strcmp(name, "accumulateIndex") == 0) {
    NSlab_accumulateIndex = in;
  }
}

NSlabPtr n_NSlab_init(PlanePtr plane, double thickness) {
  NSlabPtr slab;
  slab = malloc(sizeof(NSlab));
  memset(slab, 0, sizeof(NSlab));
  slab->plane = plane;
  slab->thickness = thickness;
  return slab;
}

void n_NSlab_print(NSlabPtr slab, const char *text) {
  ZF_LOGI("---------- Slab %s Begin ----------", text);
  ZF_LOGI("| Center   : %6.2f %6.2f %6.2f", slab->plane->center->x,
          slab->plane->center->y, slab->plane->center->z);
  ZF_LOGI("| Normal   : %6.2f %6.2f %6.2f", slab->plane->normal->x,
          slab->plane->normal->y, slab->plane->normal->z);
  ZF_LOGI("| thickness: %6.2f ", slab->thickness);
  ZF_LOGI("----------- Slab %s End -----------", text);
}

void n_NSlab_print_xml(NSlabPtr slab, const char *filename, const char *xpathText,
                      const char *slabName) {
  //char newxpath[MAX_STRING] = {0};
  // n_string_join(newxpath, xpathText, "ellipsoid", "/");
  xmlTextWriterPtr writer;
  ControlFilePtr cf = n_ControlFile_init(filename, NULL);
  xmlNodePtr node =
      n_ControlFile_get_nth_nodeset_by_xpath(cf->doc, xpathText, 0);
  writer = xmlNewTextWriterTree(cf->doc, node, 0);

  int rc;
  char temp[32];

  rc = xmlTextWriterStartElement(writer, BAD_CAST slabName);
  rc = xmlTextWriterStartElement(writer, BAD_CAST "type");
  sprintf(temp, "%s", "slab");
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For type

  rc = xmlTextWriterStartElement(writer, BAD_CAST "count");
  sprintf(temp, "%i", slab->count);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For count

  rc = xmlTextWriterStartElement(writer, BAD_CAST "center");
  rc = xmlTextWriterStartElement(writer, BAD_CAST "x");
  sprintf(temp, "%f", slab->plane->center->x);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For x
  rc = xmlTextWriterStartElement(writer, BAD_CAST "y");
  sprintf(temp, "%f", slab->plane->center->y);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For y
  rc = xmlTextWriterStartElement(writer, BAD_CAST "z");
  sprintf(temp, "%f", slab->plane->center->z);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For z
  rc = xmlTextWriterEndElement(writer); // For center

  rc = xmlTextWriterStartElement(writer, BAD_CAST "normal");
  rc = xmlTextWriterStartElement(writer, BAD_CAST "x");
  sprintf(temp, "%f", slab->plane->normal->x);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For x
  rc = xmlTextWriterStartElement(writer, BAD_CAST "y");
  sprintf(temp, "%f", slab->plane->normal->y);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For y
  rc = xmlTextWriterStartElement(writer, BAD_CAST "z");
  sprintf(temp, "%f", slab->plane->normal->z);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For z
  rc = xmlTextWriterEndElement(writer); // For normal

  rc = xmlTextWriterStartElement(writer, BAD_CAST "thickness");
  sprintf(temp, "%f", slab->thickness);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For thickness

  rc = xmlTextWriterEndElement(writer); // For geometry


  xmlFreeTextWriter(writer);

  xmlSaveFileEnc(filename, cf->doc, MY_STRUCTURE_ENCODING);

  n_ControlFile_free(cf);
}

NSlabPtr n_NSlab_init_from_file(const char *fileName,
                              const char *xpath2geometry) {
  char geometry[MAX_STRING] = {'\0'};
  char xpathText[MAX_STRING] = {'\0'};
  ControlFilePtr cf = n_ControlFile_init(fileName, NULL);
  n_string_join(xpathText, xpath2geometry, "/type", "");
  n_ControlFile_get_text_by_xpath(geometry, cf->doc, xpathText, "");
  n_string_trim(geometry, "\t\n\v\f\r ");
  if (strcmp(geometry, "slab") != 0) {
    ZF_LOGE("The geometry %s %s is not a slab, %s ", fileName, xpath2geometry,
            geometry);
    return NULL;
  }
  double centerX, centerY, centerZ;
  double normalX, normalY, normalZ, thickness;
  n_string_join(xpathText, xpath2geometry, "/centerX", "");
  centerX = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/centerY", "");
  centerY = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/centerZ", "");
  centerZ = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);

  n_string_join(xpathText, xpath2geometry, "/normalX", "");
  normalX = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 0);
  n_string_join(xpathText, xpath2geometry, "/normalY", "");
  normalY = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 0);
  n_string_join(xpathText, xpath2geometry, "/normalZ", "");
  normalZ = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/thickness", "");
  thickness = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 3);

  NPointPtr center = n_NPoint_init(centerX, centerY, centerZ);
  NPointPtr normal = n_NPoint_init(normalX, normalY, normalZ);
  PlanePtr plane = n_Plane_init(center, normal);
  NSlabPtr slab = n_NSlab_init(plane, thickness);
  n_ControlFile_free(cf);
  // n_NPoint_free(center);
  // n_NPoint_free(normal);
  // n_Plane_free(plane);
  return slab;
}

void n_NSlab_update(NSlabPtr slab, PlanePtr plane, double thickness) {
  slab->plane = plane;
  slab->thickness = thickness;
}

void n_NSlab_free(NSlabPtr slab) {
  free(slab->plane);
  free(slab);
}

int n_NPoint_within_NSlab(NPointPtr point, NSlabPtr slab) {
  double distance = n_NPoint_to_Plane_distance(point, slab->plane);
  // ZF_LOGD("the distance %f %f %f %f ",point->x,point->y,point->z,distance);
  if (2 * fabs(distance) <= slab->thickness) {
    return 1;
  } else {
    return 0;
  }
}

int n_NSlab_insert(int nx, int ny, int nz, short dat[nx][ny][nz], NSlabPtr slab,
                  int label, int matrixLabel) {
  NPointPtr point = n_NPoint_init(0, 0, 0);
  int pointWithin = 0;
  int allow = 1;
  int out = -1;
  int sum = 0;
  int sum1 = 0;
  size_t i=0;
  size_t j=0;
  size_t k=0;
  if (NSlab_allowOverlap != 1) {
    for (i = 1; i < nx + 1; i++) {
      for (j = 1; j < ny + 1; j++) {
        for (k = 1; k < nz + 1; k++) {
          if (dat[i - 1][j - 1][k - 1] != matrixLabel) {
            n_NPoint_update(point, i, j, k);
            pointWithin = n_NPoint_within_NSlab(point, slab);
            sum = pointWithin + sum;
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
  // notallow:
  if (allow == 1) {
    out = 0;
    for (i = 1; i < nx + 1; i++) {
      for (j = 1; j < ny + 1; j++) {
        for (k = 1; k < nz + 1; k++) {
          n_NPoint_update(point, i, j, k);
          pointWithin = n_NPoint_within_NSlab(point, slab);
          if (pointWithin == 1) {
            dat[i - 1][j - 1][k - 1] = (short)label;
            out = out + 1;
          }
          sum1 = dat[i - 1][j - 1][k - 1] + sum1;
        }
      }
    }
    // if (NSlab_accumulateIndex == 1) {
    //   out = label + 1;
    // } else {
    //   out = label;
    // }
    slab->count = out;
  }
  n_NPoint_free(point);
  //   ZF_LOGD("allow not allow %i %i %i %i ", allow, sum, sum1, out);
  //   ZF_LOGD("allow not allow %f %f %f %f", slab->plane->center->x,
  //   slab->plane->center->y, slab->plane->center->z, slab->thickness);

  return out; // -1 means unsuccessful insert, otherwise return the next label
}

int n_generate_NSlab_from_file(int nx, int ny, int nz, short dat[nx][ny][nz],
                              const char *fileName,
                              const char *xpath2geometry) {
  NSlabPtr slab = n_NSlab_init_from_file(fileName, xpath2geometry);
  int label;
  char xpathText[MAX_STRING] = {'\0'};
  n_string_join(xpathText, xpath2geometry, "/label", "");
  ControlFilePtr cf = n_ControlFile_init(fileName, NULL);
  label = n_ControlFile_get_int_by_xpath(cf->doc, xpathText, "", 1);
  int matrixLabel, matrixLabelGlobal;
  n_string_join(xpathText, xpath2geometry, "/matrixLabel", "");
  matrixLabelGlobal = n_ControlFile_get_int_by_xpath(cf->doc, "/input/structure/matrixLabel", "", 0);
  matrixLabel = n_ControlFile_get_int_by_xpath(cf->doc, xpathText, "", matrixLabelGlobal);

  int flag = n_NSlab_insert(nx, ny, nz, dat, slab, label, matrixLabel);
  if (flag == -1) {
    ZF_LOGI("missed an slab");
  } else {
    if (NSlab_accumulateIndex == 1) {
      label = label + 1;
    }
    n_NSlab_print(slab, "");
    n_NSlab_print_xml(slab, MY_STRUCTURE_FILE, MY_STRUCTURE_FILE_ROOT,
                     "geometry");
  }

  n_NSlab_free(slab);
  n_ControlFile_free(cf);
  return flag;
}