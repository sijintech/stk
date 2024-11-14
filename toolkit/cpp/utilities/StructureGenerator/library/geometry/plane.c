#include <nstructuregenerator/structures.h>

PlanePtr n_Plane_init(NPointPtr center, NPointPtr normal) {
  PlanePtr plane;
  plane = malloc(sizeof(Plane));
  memset(plane, 0, sizeof(Plane));
  plane->center = center;
  double tmp[3] = {normal->x, normal->y, normal->z};
  n_vector3_normalize_inplace(tmp);
  n_NPoint_update(normal, tmp[0], tmp[1], tmp[2]);
  plane->normal = normal;
  return plane;
}

void n_Plane_free(PlanePtr plane) { free(plane); }

double n_NPoint_to_Plane_distance(NPointPtr point, PlanePtr plane) {
  // ZF_LOGD("point %f %f %f",point->x,point->y,point->z);
  // ZF_LOGD("plane normal %f %f
  // %f",plane->normal->x,plane->normal->y,plane->normal->z); ZF_LOGD("plane
  // normal %f %f %f",plane->normal->x,plane->normal->y,plane->normal->z);
  // double a[3] = {point->x, point->y, point->z};
  double a[3] = {plane->normal->x, plane->normal->y, plane->normal->z};
  double b[3] = {point->x - plane->center->x, point->y - plane->center->y,
                 point->z - plane->center->z};                
  return n_vector3_dot_vector3(a,b);
  // return
  // plane->normal->x*(point->x-plane->center->x)+plane->normal->y*(point->y-plane->center->y)+plane->normal->z*(point->z-plane->center->z);
}
