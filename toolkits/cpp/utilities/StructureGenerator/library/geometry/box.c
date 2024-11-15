#include <nstructuregenerator/structures.h>

BoxPtr n_Box_init(double xmin, double xmax, double ymin, double ymax, double zmin, double zmax){
    BoxPtr box;
    box = malloc(sizeof(Box));
    memset(box, 0, sizeof(Box));
    box->xmin = xmin;
    box->xmax = xmax;
    box->ymin = ymin;
    box->ymax = ymax;
    box->zmin = zmin;
    box->zmax = zmax;
    return box;
}

void n_Box_free(BoxPtr box){
    free(box);
}

int n_NPoint_within_Box(NPointPtr point, BoxPtr box){
  return ((point->x - box->xmax) <= NZEROTHRESHOLD) &&
         ((point->x - box->xmin) >= -NZEROTHRESHOLD) &&
         ((point->y - box->ymax) <= NZEROTHRESHOLD) &&
         ((point->y - box->ymin) >= -NZEROTHRESHOLD) &&
         ((point->z - box->zmax) <= NZEROTHRESHOLD) &&
         ((point->z - box->zmin) >= -NZEROTHRESHOLD);
}