#include "nmathfft/cahnhilliard.h"

int n_fft_cahnhilliard_check_ready(NCHSolverPtr chsp){
    int check=1;
    if (chsp->link_flag_composition == 0)
    {
        check=0;
        ZF_LOGE("The composition for solver %s is not linked.",chsp->solver_name);
    }
    if (chsp->link_flag_driving_force == 0)
    {
        check=0;
        ZF_LOGE("The driving force for solver %s is not linked.",chsp->solver_name);
    }

    
    return check;
    
}
