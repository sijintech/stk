#include <effprop/effprop.h>

void pre_solve(){
}

void post_solve(){

}

void solve_distribution()
{
    if (control_dielectric == 1){
        pre_solve_distribution_dielectric();
        solve_distribution_dielectric();
    }

    if (control_diffusion == 1){
        pre_solve_distribution_diffusion();
        solve_distribution_diffusion();
    }
    if (control_electrical == 1){
        pre_solve_distribution_electrical();
        solve_distribution_electrical();
    }
    if (control_thermal == 1){
        pre_solve_distribution_thermal();
        solve_distribution_thermal();
    }
    if (control_magnetic == 1){
        pre_solve_distribution_magnetic();
        solve_distribution_magnetic();
    }
    if (control_elastic == 1){
        pre_solve_distribution_elastic();
        solve_distribution_elastic();
    }
    if (control_piezoelectric == 1){
        pre_solve_distribution_piezoelectric();
        solve_distribution_piezoelectric();
    }
    if (control_piezomagnetic == 1){
        pre_solve_distribution_piezomagnetic();
        solve_distribution_piezomagnetic();
    }
    if (control_magnetoelectric == 1){
        pre_solve_distribution_magnetoelectric();
        solve_distribution_magnetoelectric();
    }
}

void solve_effective_property(){
    if (control_dielectric == 1)
        solve_effective_property_dielectric();
    if (control_diffusion == 1)
        solve_effective_property_diffusion();
    if (control_electrical == 1)
        solve_effective_property_electrical();
    if (control_magnetic == 1)
        solve_effective_property_magnetic();
    if (control_thermal == 1)
        solve_effective_property_thermal();
    if (control_elastic == 1)
        solve_effective_property_elastic();
    if (control_piezoelectric == 1)
        solve_effective_property_piezoelectric();
    if (control_piezomagnetic == 1)
        solve_effective_property_piezomagnetic();
    if (control_magnetoelectric == 1)
        solve_effective_property_magnetoelectric();
}