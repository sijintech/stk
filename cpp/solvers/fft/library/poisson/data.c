#include <nmathfft/poisson.h>

void n_fft_poisson_string_set(NPoissonSolverPtr psp, const char *name, const char *in)
{
    if (strcmp(name, "poisson_3d/solver_name") == 0)
    {
        strcpy(psp->solver_name, in);
        n_string_join(psp->csv_filename, psp->solver_name, "csv", ".");
    }
}

void n_fft_poisson_int_set(NPoissonSolverPtr psp, const char *name, int in)
{
    if (strcmp(name, "poisson_3d/control/solver/homo") == 0)
    {
        psp->control_solver_homo = in;
    }
    else if (strcmp(name, "poisson_3d/control/external_field_nonzero") == 0)
    {
        psp->control_external_field_nonzero = in;
    }
    else if (strcmp(name, "poisson_3d/control/rhs_source_nonzero") == 0)
    {
        psp->control_rhs_source_nonzero = in;
    }
    else if (strcmp(name, "poisson_3d/control/print") == 0)
    {
        psp->control_print = in;
    }
    else if (strcmp(name, "poisson_3d/control/print_csv") == 0)
    {
        psp->control_print_csv = in;
    }
    else if (strcmp(name, "poisson_3d/control/max_iterations") == 0)
    {
        psp->max_iterations = in;
    }
    else if (strcmp(name, "poisson_3d/solver_index") == 0)
    {
        psp->solver_index = in;
    }
    else if (strcmp(name, "poisson_3d/control/auto_index_update") == 0)
    {
        psp->control_auto_index_update = in;
    }
    else if (strcmp(name, "poisson_3d/phase_count") == 0)
    {
        psp->phase_count = in;
        psp->set_flag_phase_count = 1;
    }
}

int n_fft_poisson_int_get(NPoissonSolverPtr psp, const char *name)
{
    if (strcmp(name, "poisson_3d/control/solver/homo") == 0)
    {
        return psp->control_solver_homo;
    }
    else if (strcmp(name, "poisson_3d/control/external_field_nonzero") == 0)
    {
        return psp->control_external_field_nonzero;
    }
    else if (strcmp(name, "poisson_3d/control/rhs_source_nonzero") == 0)
    {
        return psp->control_rhs_source_nonzero;
    }
    else if (strcmp(name, "poisson_3d/control/print") == 0)
    {
        return psp->control_print;
    }
    else if (strcmp(name, "poisson_3d/control/print_csv") == 0)
    {
        return psp->control_print_csv;
    }
    else if (strcmp(name, "poisson_3d/solver_index") == 0)
    {
        return psp->solver_index;
    }
    else if (strcmp(name, "poisson_3d/control/auto_index_update") == 0)
    {
        return psp->control_auto_index_update;
    }
    return -1;
}

void n_fft_poisson_double_set(NPoissonSolverPtr psp, const char *name, double in)
{
    if (strcmp(name, "poisson_3d/control/threshold") == 0)
    {
        psp->threshold = in;
    }
    else if (strcmp(name, "poisson_3d/control/iter_step") == 0)
    {
        psp->iter_step = in;
    }
}

void n_fft_poisson_double_array_set(NPoissonSolverPtr psp, const char *name, double *in)
{
    if (strcmp(name, "poisson_3d/epsilon_homo") == 0)
    {
        psp->epsilon_homo[0][0] = in[0];
        psp->epsilon_homo[0][1] = in[1];
        psp->epsilon_homo[0][2] = in[2];
        psp->epsilon_homo[1][0] = in[3];
        psp->epsilon_homo[1][1] = in[4];
        psp->epsilon_homo[1][2] = in[5];
        psp->epsilon_homo[2][0] = in[6];
        psp->epsilon_homo[2][1] = in[7];
        psp->epsilon_homo[2][2] = in[8];
        psp->set_flag_epsilon_homo = 1;
    }
    else if (strcmp(name, "poisson_3d/external_field") == 0)
    {
        psp->external_field[0] = in[0];
        psp->external_field[1] = in[1];
        psp->external_field[2] = in[2];

        psp->set_flag_external_field = 1;
    }
}

void n_fft_poisson_double_array_link(NPoissonSolverPtr psp, const char *name, double *in)
{
    if (strcmp(name, "poisson_3d/epsilon") == 0)
    {
        psp->epsilon = in;
        // ZF_LOGI("Teh delta %s %p %p %f %f",name,psp->poisson_3d_epsilon_delta,in,*in,in[0]);
        psp->link_flag_epsilon = 1;
    }
    else if (strcmp(name, "poisson_3d/potential") == 0)
    {
        psp->potential = in;
        psp->link_flag_potential = 1;
        // ZF_LOGI("Teh delta %s %p %p %f %f %f",name,psp->poisson_3d_potential,in,*in,in[0]);

        // ZF_LOGI("The potential %p %f",poisson_3d_potential,poisson_3d_potential[1]);
        // ZF_LOGI("The potential %p %f",in, in[1]);
    }
    else if (strcmp(name, "poisson_3d/field") == 0)
    {
        psp->field = in;
        psp->link_flag_field = 1;
    }
    else if (strcmp(name, "poisson_3d/rhs_source") == 0)
    {
        psp->rhs_source = in;
        psp->link_flag_rhs_source = 1;
    }
    else if (strcmp(name, "poisson_3d/energy") == 0)
    {
        psp->energy = in;
        psp->link_flag_energy = 1;
    }
}

void n_fft_poisson_short_array_link(NPoissonSolverPtr psp, const char *name, short *in)
{
    if (strcmp(name, "poisson_3d/phase") == 0)
    {
        psp->phase = in;
        psp->link_phase = 1;
    }
}
