#include <nmathfft/elastic.h>

void n_fft_elastic_print_screen(NElasticSolverPtr esp)
{
    if (esp->iteration_index % 10 == 0)
    {
        ZF_LOGI("Elastic Solver, iteration: %5i, Error: %13.6le",
                esp->iteration_index, esp->error);
    }
}

void n_fft_elastic_print_csv(NElasticSolverPtr esp)
{
    double out[3] = {esp->solver_index, esp->iteration_index, esp->error};
    n_timeFile_write_line_from_double(out, 3, esp->csv_filename);
}

void n_fft_elastic_print_csv_header(NElasticSolverPtr esp)
{
    const char* header = "solver_index,iteration,error";
    n_timeFile_write_header_line(header, esp->csv_filename);
}
