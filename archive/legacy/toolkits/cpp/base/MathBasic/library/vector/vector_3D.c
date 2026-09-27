#include "nmathbasic/nmathbasic.h"


int n_vector3_is_parallel(double a[3], double b[3])
{
    double output[3] = {0, 0, 0};
    n_vector3_cross_vector3(output, a, b);
    if (n_vector3_norm(output) < NZEROTHRESHOLD)
    {
        return 1;
    }
    else
    {
        return 0;
    }
}

int n_vector3_is_perpendicular(double a[3], double b[3])
{
    if (fabs(n_vector3_dot_vector3(a, b)) < NZEROTHRESHOLD)
    {
        return 1;
    }
    else
    {
        return 0;
    }
}

void n_vector3_normalize(double output[3], double a[3])
{
    double length = n_vector3_norm(a);
    output[0] = a[0] / length;
    output[1] = a[1] / length;
    output[2] = a[2] / length;
}

void n_vector3_normalize_inplace(double a[3])
{
    double length = n_vector3_norm(a);
    a[0] = a[0] / length;
    a[1] = a[1] / length;
    a[2] = a[2] / length;
}

double n_vector3_norm(double a[3])
{
    return sqrt(pow(a[0], 2) + pow(a[1], 2) + pow(a[2], 2));
}

void n_vector3_cross_vector3(double output[3], double a[3], double b[3])
{
    output[0] = a[1] * b[2] - b[1] * a[2];
    output[1] = a[2] * b[0] - b[2] * a[0];
    output[2] = a[0] * b[1] - b[0] * a[1];
}

double n_vector3_dot_vector3(double a[3], double b[3])
{
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}