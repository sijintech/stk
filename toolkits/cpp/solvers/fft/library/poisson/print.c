#include "nmathfft/poisson.h"

void n_fft_poisson_3d_print(NPoissonSolverPtr psp)
{
    if (psp->iteration_index % 10 == 0)
    {
        ZF_LOGI("Poisson Solver, iteration: %5i, Error: %13.6le",
                psp->iteration_index, psp->error);
    }
}

void n_fft_poisson_3d_print_csv(NPoissonSolverPtr psp)
{
    double out[3] = {psp->solver_index, psp->iteration_index, psp->error};
    n_timeFile_write_line_from_double(out, 3, psp->csv_filename);
}

void n_fft_poisson_3d_print_csv_header(NPoissonSolverPtr psp)
{
    char out[256] = "solver index, iteration index, error";
    n_timeFile_write_header_line(out, psp->csv_filename);
}