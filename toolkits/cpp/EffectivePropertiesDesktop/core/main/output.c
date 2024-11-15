#include <effprop/effprop.h>

void output_distribution()
{
    if(control_dielectric)
        output_distribution_dielectric();
    if(control_diffusion)
        output_distribution_diffusion();
    if(control_electrical)
        output_distribution_electrical();
    if(control_thermal)
        output_distribution_thermal();
    if(control_magnetic)
        output_distribution_magnetic();
    if(control_elastic)
        output_distribution_elastic();
    if(control_piezoelectric)
        output_distribution_piezoelectric();
    if(control_piezomagnetic)
        output_distribution_piezomagnetic();
    if(control_magnetoelectric)
        output_distribution_magnetoelectric();
}

void output_effective_property()
{
    if(control_dielectric)
        output_effective_property_dielectric();
    if(control_diffusion)
        output_effective_property_diffusion();
    if(control_electrical)
        output_effective_property_electrical();
    if(control_thermal)
        output_effective_property_thermal();
    if(control_magnetic)
        output_effective_property_magnetic();
    if(control_elastic)
        output_effective_property_elastic();
    if(control_piezoelectric)
        output_effective_property_piezoelectric();
    if(control_piezomagnetic)
        output_effective_property_piezomagnetic();
    if(control_magnetoelectric)
        output_effective_property_magnetoelectric();
}