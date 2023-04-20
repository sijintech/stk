#include "nmathbasic/nmathbasic.h"

void n_random_init_by_time(){
    time_t t;
    srand((unsigned) time(&t));
}

void n_random_init_by_seed(int seed){
    srand(seed);	
}

double n_random_in_range(double lower, double upper){
    return ((double)rand()/(double)RAND_MAX * (upper - lower)) + lower;
}