#include <nmathfft/nmathfft.h>
#include "variables.h"

void read_parameter();
void setup_fft();
void setup_structure();
void setup_poisson();

int main(){
    // read the parameters
    read_parameter();


    // setup fftw
    setup_fft();

    // setup the structure
    setup_structure();

    // setup the poisson solver
    setup_poisson();
    // solve the poisson equation

    // compare with analytical
}