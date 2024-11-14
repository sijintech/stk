#include "nmathbasic/nmathbasic.h"




double get_matrix22_determinant(double a[2][2])
{
    return a[0][0] * a[1][1] - a[0][1] * a[1][0];
}

void get_matrix22_inverse(double output[2][2], double input[2][2])
{
    double determinant = get_matrix22_determinant(input);
    output[0][0] = input[1][1] / determinant;
    output[0][1] = -input[0][1] / determinant;
    output[1][0] = -input[1][0] / determinant;
    output[1][1] = input[0][0] / determinant;
}