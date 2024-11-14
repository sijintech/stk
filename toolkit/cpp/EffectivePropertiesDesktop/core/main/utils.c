#include <effprop/effprop.h>

void get_nth_component(double *out, double *in, int total, int rank, int nth){

    size_t i=0;
    for (i = 0; i < total; i++)
    {
        out[i] = in[rank*i+nth];
    }
}