#ifndef __STRUCTURE_H__
#define __STRUCTURE_H__

#include "niobasic/niobasic.h"
#include <libxml/parser.h>
#include <libxml/xpath.h>
#include "niobasic/controlFile.h"
#include "nmathbasic/nmathbasic.h"
#include "nstructuregenerator/exports.h"
#include "ntextutils/ntextutils.h"
#define MY_STRUCTURE_ENCODING "UTF-8"
#define MY_STRUCTURE_FILE "structure.xml"
#define MY_STRUCTURE_FILE_ROOT "structure"
#ifdef __cplusplus
extern "C"
{
#endif

  typedef struct
  {
    double xmin, xmax;
    double ymin, ymax;
    double zmin, zmax;
  } Box;
  typedef Box *BoxPtr;

  typedef struct
  {
    double x;
    double y;
    double z;
  } NPoint;
  typedef NPoint *NPointPtr;

  typedef struct
  {
    NPointPtr center;
    NPointPtr normal;
  } Plane;
  typedef Plane *PlanePtr;

  typedef struct
  {
    PlanePtr plane;
    double thickness;
    int count;
  } NSlab;
  typedef NSlab *NSlabPtr;

  typedef struct
  {
    NPointPtr center;
    double radiusX;
    double radiusY;
    double radiusZ;
    double rotation[3][3];
    int count;
  } NEllipsoid;
  typedef NEllipsoid *NEllipsoidPtr;

  typedef struct
  {
    NEllipsoidPtr outer;
    NEllipsoidPtr inner;
    int count;
  } NEllipsoidShell;
  typedef NEllipsoidShell *NEllipsoidShellPtr;

  extern int NEllipsoidShell_allowOverlap, NEllipsoidShell_accumulateIndex,
      NEllipsoidShell_periodic;
  extern int NEllipsoid_allowOverlap, NEllipsoid_accumulateIndex,
      NEllipsoid_periodic;

  NSTRUCTUREGENERATORPUBFUN NPointPtr NSTRUCTUREGENERATORCALL
  n_NPoint_init(double x, double y, double z);
  NSTRUCTUREGENERATORPUBFUN void NSTRUCTUREGENERATORCALL
  n_NPoint_update(NPointPtr point, double x, double y, double z);
  NSTRUCTUREGENERATORPUBFUN void NSTRUCTUREGENERATORCALL
  n_NPoint_free(NPointPtr point);

  NSTRUCTUREGENERATORPUBFUN PlanePtr NSTRUCTUREGENERATORCALL
  n_Plane_init(NPointPtr center, NPointPtr normal);
  NSTRUCTUREGENERATORPUBFUN void NSTRUCTUREGENERATORCALL
  n_Plane_free(PlanePtr plane);
  NSTRUCTUREGENERATORPUBFUN double NSTRUCTUREGENERATORCALL
  n_NPoint_to_Plane_distance(NPointPtr point, PlanePtr plane);

  NSTRUCTUREGENERATORPUBFUN NSlabPtr NSTRUCTUREGENERATORCALL
  n_NSlab_init(PlanePtr plane, double thickness);
  NSTRUCTUREGENERATORPUBFUN void NSTRUCTUREGENERATORCALL
  n_NSlab_free(NSlabPtr slab);
  NSTRUCTUREGENERATORPUBFUN void NSTRUCTUREGENERATORCALL
  n_NSlab_print(NSlabPtr slab, const char *text);
  NSTRUCTUREGENERATORPUBFUN void NSTRUCTUREGENERATORCALL
  n_NSlab_print_xml(NSlabPtr slab, const char *filename, const char *xpathText,
                   const char *slabName);
  NSTRUCTUREGENERATORPUBFUN int NSTRUCTUREGENERATORCALL
  n_NPoint_within_NSlab(NPointPtr point, NSlabPtr slab);
NSTRUCTUREGENERATORPUBFUN NSlabPtr NSTRUCTUREGENERATORCALL n_NSlab_init_from_file(const char *fileName,
                              const char *xpath2geometry);

  NSTRUCTUREGENERATORPUBFUN BoxPtr NSTRUCTUREGENERATORCALL
  n_Box_init(double xmin, double xmax, double ymin, double ymax, double zmin,
             double zmax);
  NSTRUCTUREGENERATORPUBFUN void NSTRUCTUREGENERATORCALL n_Box_free(BoxPtr point);
  NSTRUCTUREGENERATORPUBFUN int NSTRUCTUREGENERATORCALL
  n_NPoint_within_Box(NPointPtr point, BoxPtr box);

  NSTRUCTUREGENERATORPUBFUN NEllipsoidPtr NSTRUCTUREGENERATORCALL
  n_NEllipsoid_init(NPointPtr point, double radiusX, double radiusY, double radiusZ,
                   double rotationX, double rotationY, double rotationZ);
  NSTRUCTUREGENERATORPUBFUN NEllipsoidPtr NSTRUCTUREGENERATORCALL
  n_NEllipsoid_init_from_file(const char *fileName, const char *xpath2geometry);
  NSTRUCTUREGENERATORPUBFUN void NSTRUCTUREGENERATORCALL
  n_NEllipsoid_free(NEllipsoidPtr ellipsoid);
  NSTRUCTUREGENERATORPUBFUN int NSTRUCTUREGENERATORCALL
  n_NPoint_within_NEllipsoid(NPointPtr point, NEllipsoidPtr ellipsoid);
  NSTRUCTUREGENERATORPUBFUN double NSTRUCTUREGENERATORCALL
  n_NEllipsoid_volume(NEllipsoidPtr ellipsoid);
  NSTRUCTUREGENERATORPUBFUN int NSTRUCTUREGENERATORCALL
  n_NEllipsoid_insert(int nx, int ny, int nz, short dat[nx][ny][nz],
                     NEllipsoidPtr ellipsoid, int label, int matrixLabel);
  NSTRUCTUREGENERATORPUBFUN void NSTRUCTUREGENERATORCALL
  n_NEllipsoid_print(NEllipsoidPtr ellipsoid, const char *text);
  NSTRUCTUREGENERATORPUBFUN void NSTRUCTUREGENERATORCALL
  n_NEllipsoid_print_xml(NEllipsoidPtr ellipsoid, const char *text,
                        const char *xpathText, const char *ellipsoidName);
  NSTRUCTUREGENERATORPUBFUN void NSTRUCTUREGENERATORCALL
  n_NEllipsoid_print_xml_by_writer(NEllipsoidPtr ellipsoid, xmlTextWriterPtr writer,
                                  const char *ellipsoidName);
  NSTRUCTUREGENERATORPUBFUN NEllipsoidPtr NSTRUCTUREGENERATORCALL
  n_NEllipsoid_random_init(BoxPtr box, BoxPtr radiusBox, BoxPtr angleBox);
  NSTRUCTUREGENERATORPUBFUN NEllipsoidPtr NSTRUCTUREGENERATORCALL
  n_NEllipsoid_random_scale_init(BoxPtr box, double radiusX, double radiusY,
                                double radiusZ, BoxPtr angleBox, double scaleMin,
                                double scaleMax);

  NSTRUCTUREGENERATORPUBFUN NEllipsoidShellPtr NSTRUCTUREGENERATORCALL
  n_NEllipsoidShell_init(NEllipsoidPtr outer, NEllipsoidPtr inner);
  NSTRUCTUREGENERATORPUBFUN NEllipsoidShellPtr NSTRUCTUREGENERATORCALL
  n_NEllipsoidShell_init_from_file(const char *fileName,
                                  const char *xpath2geometry);
  NSTRUCTUREGENERATORPUBFUN void NSTRUCTUREGENERATORCALL
  n_NEllipsoidShell_free(NEllipsoidShellPtr ellipsoid);
  NSTRUCTUREGENERATORPUBFUN double NSTRUCTUREGENERATORCALL
  n_NEllipsoidShell_volume(NEllipsoidShellPtr ellipsoidShell);
  NSTRUCTUREGENERATORPUBFUN int NSTRUCTUREGENERATORCALL
  n_NPoint_within_NEllipsoidShell(NPointPtr point, NEllipsoidShellPtr ellipsoid);
  NSTRUCTUREGENERATORPUBFUN int NSTRUCTUREGENERATORCALL n_NEllipsoidShell_insert(
      int nx, int ny, int nz, short dat[nx][ny][nz], NEllipsoidShellPtr ellipsoid,
      int label, int innerLabel, int matrixLabel);
  NSTRUCTUREGENERATORPUBFUN void NSTRUCTUREGENERATORCALL
  n_NEllipsoidShell_print(NEllipsoidShellPtr ellipsoid, const char *text);
  NSTRUCTUREGENERATORPUBFUN void NSTRUCTUREGENERATORCALL
  n_NEllipsoidShell_print_xml(NEllipsoidShellPtr ellipsoid, const char *text,
                             const char *xpathText,
                             const char *ellipsoidShellName);
  NSTRUCTUREGENERATORPUBFUN void NSTRUCTUREGENERATORCALL
  n_NEllipsoidShell_print_xml_by_writer(NEllipsoidShellPtr ellipsoid,
                                       xmlTextWriterPtr writer,
                                       const char *ellipsoidShellName);
  NSTRUCTUREGENERATORPUBFUN NEllipsoidShellPtr NSTRUCTUREGENERATORCALL
  n_NEllipsoidShell_random_init(BoxPtr box, BoxPtr radiusBox, BoxPtr angleBox,
                               double thickMin, double thickMax);
  NSTRUCTUREGENERATORPUBFUN NEllipsoidShellPtr NSTRUCTUREGENERATORCALL
  n_NEllipsoidShell_random_scale_init(BoxPtr box, double radiusX, double radiusY, double radiusZ,
                                     BoxPtr angleBox, double thickMin,
                                     double thickMax, double scaleMin,
                                     double scaleMax);

  NSTRUCTUREGENERATORPUBFUN int NSTRUCTUREGENERATORCALL
  n_generate_NEllipsoid_from_file(int nx, int ny, int nz, short dat[nx][ny][nz],
                                 const char *fileName,
                                 const char *xpath2geometry);
  NSTRUCTUREGENERATORPUBFUN int NSTRUCTUREGENERATORCALL
  n_generate_NEllipsoidShell_from_file(int nx, int ny, int nz, short dat[nx][ny][nz],
                                      const char *fileName,
                                      const char *xpath2geometry);
  NSTRUCTUREGENERATORPUBFUN int NSTRUCTUREGENERATORCALL
  n_generate_NEllipsoid_random_from_file(int nx, int ny, int nz,
                                        short dat[nx][ny][nz], const char *fileName,
                                        const char *xpath2geometry);
  NSTRUCTUREGENERATORPUBFUN int NSTRUCTUREGENERATORCALL
  n_generate_NEllipsoid_random_scale_from_file(int nx, int ny, int nz,
                                              short dat[nx][ny][nz],
                                              const char *fileName,
                                              const char *xpath2geometry);
  NSTRUCTUREGENERATORPUBFUN int NSTRUCTUREGENERATORCALL
  n_generate_NEllipsoidShell_random_from_file(int nx, int ny, int nz,
                                             short dat[nx][ny][nz],
                                             const char *fileName,
                                             const char *xpath2geometry);
  NSTRUCTUREGENERATORPUBFUN int NSTRUCTUREGENERATORCALL
  n_generate_NEllipsoidShell_random_scale_from_file(int nx, int ny, int nz,
                                                   short dat[nx][ny][nz],
                                                   const char *fileName,
                                                   const char *xpath2geometry);
  NSTRUCTUREGENERATORPUBFUN int NSTRUCTUREGENERATORCALL
  n_generate_NSlab_from_file(int nx, int ny, int nz, short dat[nx][ny][nz],
                            const char *fileName, const char *xpath2geometry);

#ifdef __cplusplus
}
#endif
#endif