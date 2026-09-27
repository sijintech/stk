#include <effprop/effprop.h>

void pre_initialize()
{
}

void post_initialize()
{
}

void initialize()
{
    zero = calloc(nx * ny * nz, sizeof(double));
    tmp = calloc(nx * ny * nz, sizeof(double));
    tmp1 = calloc(nx * ny * nz, sizeof(double));
    
    initialize_fft();
    initialize_structure();
    
    if (control_dielectric == 1)
        initialize_dielectric();
    if (control_diffusion == 1)
        initialize_diffusion();
    if (control_electrical == 1)
        initialize_electrical();     
    if (control_thermal == 1)
        initialize_thermal(); 
    if (control_magnetic == 1)
        initialize_magnetic();       
    if (control_elastic ==1 )
        initialize_elastic();
    if (control_piezoelectric ==1 )
        initialize_piezoelectric(); 
    if (control_piezomagnetic ==1 )
        initialize_piezomagnetic(); 
    if (control_magnetoelectric ==1 )
        initialize_magnetoelectric(); 
}

void pre_destruct()
{
}

void post_destruct()
{
}

void destruct()
{
    free(zero);
    free(tmp);
    free(tmp1);
    destruct_fft();
    destruct_structure();
    
    if (control_dielectric == 1)
        destruct_dielectric();
    if (control_diffusion == 1)
        destruct_diffusion();    
    if (control_electrical == 1)
        destruct_electrical();
    if (control_thermal == 1)
        destruct_thermal();    
    if (control_elastic==1)
        destruct_elastic();
}
