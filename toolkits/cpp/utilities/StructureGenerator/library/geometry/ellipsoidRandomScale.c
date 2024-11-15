#include <nstructuregenerator/structures.h>

int ellipsoid_random_scale_iter_max = 1000;

NEllipsoidPtr n_NEllipsoid_random_scale_init(BoxPtr box, double radiusX,
                                           double radiusY, double radiusZ,
                                           BoxPtr angleBox, double scaleMin,
                                           double scaleMax) {
  double scale = n_random_in_range(scaleMin, scaleMax);
  double X = n_random_in_range(box->xmin, box->xmax);
  double Y = n_random_in_range(box->ymin, box->ymax);
  double Z = n_random_in_range(box->zmin, box->zmax);
  NPointPtr center = n_NPoint_init(X, Y, Z);
  // ZF_LOGD("random number for ellipsoid random scale %f, %f, %f", X, Y, Z);

  double angleX = n_random_in_range(angleBox->xmin, angleBox->xmax);
  double angleY = n_random_in_range(angleBox->ymin, angleBox->ymax);
  double angleZ = n_random_in_range(angleBox->zmin, angleBox->zmax);

  return n_NEllipsoid_init(center, scale * radiusX, scale * radiusY,
                          scale * radiusZ, angleX, angleY, angleZ);
}

int n_generate_NEllipsoid_random_scale_from_file(int nx, int ny, int nz,
                                                short dat[nx][ny][nz],
                                                const char *fileName,
                                                const char *xpath2geometry) {
  char geometry[MAX_STRING] = {'\0'};
  char xpathText[MAX_STRING] = {'\0'};
  ControlFilePtr cf = n_ControlFile_init(fileName, NULL);
  int count = 0, label = 0, flag = 0, success_count = 0, iter_count = 0,
      matrixLabel, matrixLabelGlobal;
  n_string_join(xpathText, xpath2geometry, "/type", "");
  n_ControlFile_get_text_by_xpath(geometry, cf->doc, xpathText, "");
  if (strcmp(geometry, "ellipsoid_random_scale") != 0) {
    ZF_LOGE("The geometry %s %s is not a random scaled ellipsoid ", fileName,
            xpath2geometry);
  } else {
    ZF_LOGI("Random size ellipsoid");
  }

  n_string_join(xpathText, xpath2geometry, "/label", "");
  label = n_ControlFile_get_int_by_xpath(cf->doc, xpathText, "", 1);

  double centerXMin, centerYMin, centerZMin;
  double centerXMax, centerYMax, centerZMax;
  double radiusX, radiusY, radiusZ;
  double rotationXMin, rotationYMin, rotationZMin;
  double rotationXMax, rotationYMax, rotationZMax;
  double scaleMin, scaleMax;

  n_string_join(xpathText, xpath2geometry, "/centerXMin", "");
  centerXMin = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/centerXMax", "");
  centerXMax = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/centerYMin", "");
  centerYMin = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/centerYMax", "");
  centerYMax = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/centerZMin", "");
  centerZMin = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/centerZMax", "");
  centerZMax = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  BoxPtr centerBox = n_Box_init(centerXMin, centerXMax, centerYMin, centerYMax,
                                centerZMin, centerZMax);

  n_string_join(xpathText, xpath2geometry, "/radiusX", "");
  radiusX = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/radiusY", "");
  radiusY = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/radiusZ", "");
  radiusZ = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);

  n_string_join(xpathText, xpath2geometry, "/rotationXMin", "");
  rotationXMin = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 0);
  n_string_join(xpathText, xpath2geometry, "/rotationXMax", "");
  rotationXMax = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 0);
  n_string_join(xpathText, xpath2geometry, "/rotationYMin", "");
  rotationYMin = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 0);
  n_string_join(xpathText, xpath2geometry, "/rotationYMax", "");
  rotationYMax = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 0);
  n_string_join(xpathText, xpath2geometry, "/rotationZMin", "");
  rotationZMin = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 0);
  n_string_join(xpathText, xpath2geometry, "/rotationZMax", "");
  rotationZMax = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 0);
  BoxPtr rotationBox = n_Box_init(rotationXMin, rotationXMax, rotationYMin,
                                  rotationYMax, rotationZMin, rotationZMax);

  n_string_join(xpathText, xpath2geometry, "/count", "");
  count = n_ControlFile_get_int_by_xpath(cf->doc, xpathText, "", 1);

  n_string_join(xpathText, xpath2geometry, "/scaleMin", "");
  scaleMin = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);
  n_string_join(xpathText, xpath2geometry, "/scaleMax", "");
  scaleMax = n_ControlFile_get_double_by_xpath(cf->doc, xpathText, "", 1);

  n_string_join(xpathText, xpath2geometry, "/matrixLabel", "");
  matrixLabelGlobal = n_ControlFile_get_int_by_xpath(cf->doc, "/input/structure/matrixLabel", "", 0);
  matrixLabel = n_ControlFile_get_int_by_xpath(cf->doc, xpathText, "", matrixLabelGlobal);


  n_ControlFile_free(cf);

  int rc = 0;
  char temp[32];
  xmlTextWriterPtr writer;
  n_string_concat(xpathText, 2, "/", MY_STRUCTURE_FILE_ROOT);
  ControlFilePtr cfout =
      n_ControlFile_init(MY_STRUCTURE_FILE, MY_STRUCTURE_FILE_ROOT);

  writer = xmlNewTextWriterTree(cfout->doc, cfout->root, 0);
  rc = xmlTextWriterStartElement(writer, BAD_CAST "geometry");
  rc = xmlTextWriterStartElement(writer, BAD_CAST "type");
  sprintf(temp, "%s", "ellipsoid_random_scale");
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For type

  int volume_count = 0;
  do {
    NEllipsoidPtr ellipsoid = n_NEllipsoid_random_scale_init(
        centerBox, radiusX, radiusY, radiusZ, rotationBox, scaleMin, scaleMax);
    flag = n_NEllipsoid_insert(nx, ny, nz, dat, ellipsoid, label, matrixLabel);
    if (flag == -1) {
      // insert ellipsoid not successful
      iter_count = iter_count + 1;
      ZF_LOGI("missed an ellipsoid");
    } else {
      // insert ellipsoid successful
      // ZF_LOGD("Create an ellipsoid %f %f
      // %f",ellipsoid->center->x,ellipsoid->center->y,ellipsoid->center->z);
      if (NEllipsoid_accumulateIndex == 1) {
        label = label + 1;
      }
      n_NEllipsoid_print(ellipsoid, "");
      n_NEllipsoid_print_xml_by_writer(ellipsoid, writer, "ellipsoid");
      volume_count = volume_count + ellipsoid->count;
      success_count = success_count + 1;
      iter_count = 0;
    }
    n_NEllipsoid_free(ellipsoid);
  } while (success_count < count &&
           iter_count < ellipsoid_random_scale_iter_max);

  rc = xmlTextWriterStartElement(writer, BAD_CAST "count");
  sprintf(temp, "%i", volume_count);
  rc = xmlTextWriterWriteString(writer, BAD_CAST temp);
  rc = xmlTextWriterEndElement(writer); // For count

  // ZF_LOGD("check the numbers for ellipsoid random scale %i, %i, %i,
  // %i",success_count, count, iter_count,label);
  rc = xmlTextWriterEndElement(writer); // For geometry
  xmlFreeTextWriter(writer);
  xmlSaveFileEnc(MY_STRUCTURE_FILE, cfout->doc, MY_STRUCTURE_ENCODING);
  n_ControlFile_free(cfout);
  n_Box_free(centerBox);
  n_Box_free(rotationBox);
  return volume_count;
}