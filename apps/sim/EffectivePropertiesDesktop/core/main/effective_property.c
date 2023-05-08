#include <effprop/effprop.h>
#include <nlicense/nlicense.h>
void effective_property()
{

    // Read information from the input files
    load_input();

    // Before use the parameters, we need to normalize them to make it easier
    // for our calculations
    normalize();

    // Array allocation and
    initialize();

    if (distribution == 1)
    {
        // solve for the distribution
        solve_distribution();
        // the final output
        output_distribution();
    }

    // apply small excitation and solve for the effective property
    solve_effective_property();

    // the final output
    output_effective_property();

    // garbage collection
    destruct();
}