#include <nstructuregenerator/structures.h>

NPointPtr n_NPoint_init(double x, double y, double z){
    NPointPtr point;
    point = malloc(sizeof(NPoint));
    memset(point,0,sizeof(NPoint));
    point->x=x;
    point->y=y;
    point->z=z;
    return point;
}

void n_NPoint_update(NPointPtr point, double x, double y, double z){
    point->x=x;
    point->y=y;
    point->z=z;
}

void n_NPoint_free(NPointPtr point){
    free(point);
}


