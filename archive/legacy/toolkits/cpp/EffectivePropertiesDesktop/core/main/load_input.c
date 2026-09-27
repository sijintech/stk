#include <effprop/effprop.h>

void pre_load_input()
{
}

void post_load_input()
{
}

void load_input()
{
    pre_load_input();

    load_input_dimension();

    load_input_control();

    if (control_dielectric == 1)
        load_input_dielectric();
    if (control_diffusion == 1)
        load_input_diffusion();
    if (control_electrical == 1)
        load_input_electrical();
    if (control_thermal == 1)
        load_input_thermal();
    if (control_magnetic == 1)
        load_input_magnetic();
    if (control_elastic==1)
        load_input_elastic();
    if (control_piezoelectric==1)
        load_input_piezoelectric();    
    if (control_piezomagnetic==1)
        load_input_piezomagnetic();    
    if (control_magnetoelectric==1)
        load_input_magnetoelectric();            
    post_load_input();
}
