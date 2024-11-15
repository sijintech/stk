#include <effprop/effprop.h>

void initialize_structure(){
    phase=calloc(nx*ny*nz, sizeof(short));
    n_generate_structure_from_file(nx,ny,nz,NPTR2ARR3D(short,phase,nx,ny,nz),"input.xml","/input/structure");
    ZF_LOGI("Structure initialized");
}

void destruct_structure(){
    free(phase);
}
