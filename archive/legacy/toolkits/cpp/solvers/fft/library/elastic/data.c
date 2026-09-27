#include <nmathbasic/nmathbasic.h>
#include <nmathfft/elastic.h>
#include <nstructuregenerator/structuregenerator.h>

void n_fft_elastic_string_set(NElasticSolverPtr esp, const char* name,
                              const char* in)
{
    if (strcmp(name, "elastic_3d/solver_name") == 0)
    {
        strcpy(esp->solver_name, in);
        n_string_join(esp->csv_filename, esp->solver_name, "csv", ".");
    }
}

void n_fft_elastic_int_set(NElasticSolverPtr esp, const char* name, int in)
{
    if (strcmp(name, "elastic_3d/control/constrain_type") == 0)
    {
        esp->control_constrain_type = in;
        esp->set_flag_constrain = 1;
    }
    else if (strcmp(name, "elastic_3d/control/print") == 0)
    {
        esp->control_print = in;
    }
    else if (strcmp(name, "elastic_3d/control/print_csv") == 0)
    {
        esp->control_print_csv = in;
    }
    else if (strcmp(name, "elastic_3d/solver_index") == 0)
    {
        esp->solver_index = in;
    }
    else if (strcmp(name, "elastic_3d/control/auto_index_update") == 0)
    {
        esp->control_auto_index_update = in;
    }
    else if (strcmp(name, "elastic_3d/control/max_iterations") == 0)
    {
        esp->max_iterations = in;
    }
    else if (strcmp(name, "elastic_3d/phase_count") == 0)
    {
        esp->phase_count = in;
        esp->set_flag_phase_count = 1;
    }
}

int n_fft_elastic_int_get(NElasticSolverPtr esp, const char* name)
{
    if (strcmp(name, "elastic_3d/control/constrain_type") == 0)
    {
        return esp->control_constrain_type;
    }
    else if (strcmp(name, "elastic_3d/control/print") == 0)
    {
        return esp->control_print;
    }
    else if (strcmp(name, "elastic_3d/control/print_csv") == 0)
    {
        return esp->control_print_csv;
    }
    else if (strcmp(name, "elastic_3d/solver_index") == 0)
    {
        return esp->solver_index;
    }
    else if (strcmp(name, "elastic_3d/control/auto_index_update") == 0)
    {
        return esp->control_auto_index_update;
    }
    return -1;
}

void n_fft_elastic_double_set(NElasticSolverPtr esp, const char* name,
                              double in)
{
    if (strcmp(name, "elastic_3d/control/threshold") == 0)
    {
        esp->threshold = in;
    }
}

void n_fft_elastic_double_array_set(NElasticSolverPtr esp, const char* name,
                                    double* in)
{
    size_t i = 0;
    size_t j = 0;
    size_t k = 0;
    size_t l = 0;
    if (strcmp(name, "elastic_3d/stiffness_homo") == 0)
    {
        for (i = 0; i < 3; i++)
        {
            for (j = 0; j < 3; j++)
            {
                for (k = 0; k < 3; k++)
                {
                    for (l = 0; l < 3; l++)
                    {
                        esp->stiffness_homo[i][j][k][l] =
                            in[l + 3 * k + 9 * j + 27 * i];
                    }
                }
            }
        }

        // ZF_LOGI("Teh delta %s %p %p %f
        // %f",name,psp->poisson_3d_epsilon_delta,in,*in,in[0]);
        esp->set_flag_stiffness_homo = 1;
    }
    else if (strcmp(name, "elastic_3d/strain_avg") == 0)
    {
        esp->strain_avg[0][0] = in[0];
        esp->strain_avg[0][1] = in[1];
        esp->strain_avg[0][2] = in[2];
        esp->strain_avg[1][0] = in[3];
        esp->strain_avg[1][1] = in[4];
        esp->strain_avg[1][2] = in[5];
        esp->strain_avg[2][0] = in[6];
        esp->strain_avg[2][1] = in[7];
        esp->strain_avg[2][2] = in[8];
        esp->set_flag_strain_avg = 1;
    }
    else if (strcmp(name, "elastic_3d/stress_avg") == 0)
    {
        esp->stress_avg[0][0] = in[0];
        esp->stress_avg[0][1] = in[1];
        esp->stress_avg[0][2] = in[2];
        esp->stress_avg[1][0] = in[3];
        esp->stress_avg[1][1] = in[4];
        esp->stress_avg[1][2] = in[5];
        esp->stress_avg[2][0] = in[6];
        esp->stress_avg[2][1] = in[7];
        esp->stress_avg[2][2] = in[8];
        esp->set_flag_stress_avg = 1;
    }
}

void n_fft_elastic_double_array_link(NElasticSolverPtr esp, const char* name,
                                     double* in)
{
    if (strcmp(name, "elastic_3d/stiffness") == 0)
    {
        esp->stiffness = in;
        // ZF_LOGI("Teh delta %s %p %p %f
        // %f",name,psp->poisson_3d_epsilon_delta,in,*in,in[0]);
        esp->link_flag_stiffness = 1;
    }
    else if (strcmp(name, "elastic_3d/strain") == 0)
    {
        esp->strain = in;
        esp->link_flag_strain = 1;
    }
    else if (strcmp(name, "elastic_3d/stress") == 0)
    {
        esp->stress = in;
        esp->link_flag_stress = 1;
    }
    else if (strcmp(name, "elastic_3d/displacement") == 0)
    {
        esp->displacement = in;
        esp->link_flag_displacement = 1;
    }
    else if (strcmp(name, "elastic_3d/strain_eigen") == 0)
    {
        esp->strain_eigen = in;
        esp->link_flag_strain_eigen = 1;
    }
    else if (strcmp(name, "elastic_3d/energy") == 0)
    {
        esp->energy = in;
        esp->link_flag_energy = 1;
    }
}

void n_fft_elastic_short_array_link(NElasticSolverPtr esp, const char* name,
                                    short* in)
{
    if (strcmp(name, "elastic_3d/phase") == 0)
    {
        esp->phase = in;
        esp->link_phase = 1;
    }
}
