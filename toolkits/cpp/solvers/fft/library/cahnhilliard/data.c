#include <nmathfft/cahnhilliard.h>

void n_fft_cahnhilliard_string_set(NCHSolverPtr chsp,const char *name, const char *in){
    if (strcmp(name, "cahnhilliard_3d/solver_name") == 0)
    {
        strcpy(chsp->solver_name,in);
    }
}

void n_fft_cahnhilliard_int_set(NCHSolverPtr chsp, const char *name, int in)
{
}

int n_fft_cahnhilliard_int_get(NCHSolverPtr chsp, const char *name)
{
    return 0;
}

void n_fft_cahnhilliard_double_set(NCHSolverPtr chsp, const char *name, double in){
    if (strcmp(name, "cahnhilliard_3d/kappa") == 0)
    {
        chsp->kappa = in;
    }
    else if (strcmp(name, "cahnhilliard_3d/M") == 0)
    {
        chsp->M = in;
    }
    else if (strcmp(name, "cahnhilliard_3d/c0") == 0)
    {
        chsp->c0 = in;
    }
    else if (strcmp(name, "cahnhilliard_3d/dt") == 0)
    {
        chsp->dt = in;
    }
}

void n_fft_cahnhilliard_double_array_set(NCHSolverPtr chsp, const char *name, double *in)
{
    // if (strcmp(name, "poisson_3d/external_field") == 0)
    // {
    //     psp->external_field[0] = in[0];
    //     psp->external_field[1] = in[1];
    //     psp->external_field[2] = in[2];

    //     psp->set_flag_external_field = 1;
    // }
}

void n_fft_cahnhilliard_double_array_link(NCHSolverPtr chsp, const char *name, double *in)
{
    if (strcmp(name, "cahnhilliard_3d/driving_force") == 0)
    {
        chsp->driving_force = in;
        chsp->link_flag_driving_force = 1;
    }
    else if (strcmp(name, "cahnhilliard_3d/composition") == 0)
    {
        chsp->composition = in;
        chsp->link_flag_composition = 1;
    }
}

void n_fft_cahnhilliard_short_array_link(NCHSolverPtr chsp, const char *name, short *in)
{
    // if (strcmp(name,"poisson_3d/phase") == 0)
    // {
    //     psp->phase = in;
    //     psp->link_phase = 1;
    // }
}
