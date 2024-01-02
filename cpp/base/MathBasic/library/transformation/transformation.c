#include "nmathbasic/nmathbasic.h"

double n_unit_cell_volume(double a, double b, double c, double alpha, double beta, double gamma)
{
    return a * b * c * sqrt(1 - pow(cos(alpha), 2) - pow(cos(beta), 2) - pow(cos(gamma), 2) + 2 * cos(alpha) * cos(beta) * cos(gamma));
}

double n_parallelogram_area(double a, double b, double alpha)
{
    return a * b * cos(alpha);
}




/**
 * This function can get the transformation matrix between two coordinate system
 * One of the coordinate system is implicitly defined as x=(1,0,0), y=(0,1,0), z=(0,0,1)
 * The other coordinate system is the input value.
 * The returned Q matrix is the transformation from the coordinate value of user input system 
 * to the implicitly defined cartesian coordinate.
 * Simple derivation is as follows
 * A=a1*x1+b1*y1+c1*z1 = a2*x2+b2*y2+c2*z2, in which A is a vector, a,b,c are scalars, x,y,z are vectors
 * Suppose x1, y1, z1 is the implicit cartesian coordinate, x2, y2, z2 is the user input coordinate system
 * a1*x1.x1 = a2*x2.x1+b*y2.x1+c*z2.x1
 * b1*x1.y1 = a2*x2.y1+b*y2.y1+c*z2.y1
 * c1*x1.z1 = a2*x2.z1+b*y2.z1+c*z2.z1
 * Rewrite in the matrix form
 * |a1|   |x2.x1 y2.x1 z2.x1|   |a2|  
 * |b1| = |x2.y1 y2.y1 z2.y1| . |b2|
 * |c1|   |x2.z1 y2.z1 z2.z1|   |c2|
 * @param[out] Q[3][3]
 */
void n_transformation_matrix_by_coordinate(double Q[3][3], double x2[3], double y2[3], double z2[3])
{
    Q[0][0] = x2[0];
    Q[0][1] = y2[0];
    Q[0][2] = z2[0];
    Q[1][0] = x2[1];
    Q[1][1] = y2[1];
    Q[1][2] = z2[1];
    Q[2][0] = x2[2];
    Q[2][1] = y2[2];
    Q[2][2] = z2[2];
}

/**
 * Transform a vector from one coordinate system to another by applying the transformation matrix
 * output = Q.input
 * @param[out] output[3]
 */
void n_matrix33_multiply_vector3(double output[3], double Q[3][3], double input[3])
{
    output[0] = Q[0][0] * input[0] + Q[0][1] * input[1] + Q[0][2] * input[2];
    output[1] = Q[1][0] * input[0] + Q[1][1] * input[1] + Q[1][2] * input[2];
    output[2] = Q[2][0] * input[0] + Q[2][1] * input[1] + Q[2][2] * input[2];
}

void multiply_matrix22_vector2(double output[2], double Q[2][2], double input[2])
{
    output[0] = Q[0][0] * input[0] + Q[0][1] * input[1];
    output[1] = Q[1][0] * input[0] + Q[1][1] * input[1];
}

void n_matrix33_multiply_matrix33(double Q[3][3], double a[3][3], double b[3][3])
{
    int i=0;
    int j=0;
    for (i = 0; i < 3; i++)
    {
        for (j = 0; j < 3; j++)
        {
            Q[i][j] = a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j];
        }
    }
}

/**
 * To transform the coordinate system from a general unit cell to the cartesian system, which we call the crystal coordinate,
 * we assume the X axis in cartesian system is the same as the a axis in the lattice coordinate.
 * we also assume the xy plane of the cartesian coordinate is the same as the xy plane in
 * @param[out] Q[3][3] : the result transformation matrix from lattice to crystal, *coordinate in crystal coordinate*=Q.*coordinate in lattice coordinate*
 * @param[in] a ： the lattice constant a
 * @param[in] b ： the lattice constant b
 * @param[in] c ： the lattice constant c
 * @param[in] alpha: the lattice angle opposite of the edge a
 * @param[in] beta: the lattice angle opposite of the edge b
 * @param[in] gamma: the lattice angle opposite of the edge c
 */
void n_transformation_matrix_lattice_to_crystal(double Q[3][3], double a, double b, double c, double alpha, double beta, double gamma)
{
    /* The distance between c edge vertex point to the ab plane*/
    double height = n_unit_cell_volume(a, b, c, alpha, beta, gamma) / n_parallelogram_area(a, b, gamma);
    /* the coordinate of lattice (1,0,0) within crystal coordinate */
    double x_lat[3] = {a, 0, 0};
    /* the coordinate of lattice (0,1,0) within crystal coordinate, needs to be updated later */
    double y_lat[3] = {b * cos(gamma), b * sin(gamma), 0};
    /* the coordinate of lattice (0,0,1) within crystal coordinate, needs to be updated later */
    double z_lat[3] = {c * cos(beta), sqrt(pow(c * sin(beta), 2) - pow(height, 2)), height};
    // double x_cry[3] = {1, 0, 0};
    // double y_cry[3] = {0, 1, 0};
    // double z_cry[3] = {0, 0, 1};
    /* Get the transformation matrix from lattice coordinate to crystal coordinate */
    n_transformation_matrix_by_coordinate(Q, x_lat, y_lat, z_lat);
}

/**
 * Get the transformation matrix for the rotation of a coordinate system around arbitrary axis with specified angle
 * 
 */
void n_transformation_matrix_axis_angle(double Q[3][3], double axis[3], double angle)
{
    double temp[3][3]={0};
    double tmp1[3][3]={0};
    tmp1[0][0] = Q[0][0] ; tmp1[0][1] = Q[0][1] ; tmp1[0][2] = Q[0][2] ; 
    tmp1[1][0] = Q[1][0] ; tmp1[1][1] = Q[1][1] ; tmp1[1][2] = Q[1][2] ; 
    tmp1[2][0] = Q[2][0] ; tmp1[2][1] = Q[2][1] ; tmp1[2][2] = Q[2][2] ; 

    temp[0][0] = cos(angle) + pow(axis[0], 2) * (1 - cos(angle));
    temp[0][1] = axis[0] * axis[1] * (1 - cos(angle)) - axis[2] * sin(angle);
    temp[0][2] = axis[0] * axis[2] * (1 - cos(angle)) + axis[1] * sin(angle);

    temp[1][0] = axis[1] * axis[0] * (1 - cos(angle)) + axis[2] * sin(angle);
    temp[1][1] = cos(angle) + pow(axis[1], 2) * (1 - cos(angle));
    temp[1][2] = axis[1] * axis[2] * (1 - cos(angle)) - axis[0] * sin(angle);

    temp[2][0] = axis[2] * axis[0] * (1 - cos(angle)) - axis[1] * sin(angle);
    temp[2][1] = axis[2] * axis[1] * (1 - cos(angle)) + axis[0] * sin(angle);
    temp[2][2] = cos(angle) + pow(axis[2], 2) * (1 - cos(angle));

    n_matrix33_multiply_matrix33(Q,temp,tmp1);
}

/**
 * Get the transformation matrix for the from the crystal coordinate to lab coordinate, by defining the surface of the sample 
 * and a angle for rotation around the surface normal direction.
 * We assume that the surface normal is the Z direction of the lab coordinate.
 * X axis with rotation angle 0 is defined as the cross product of [lab coordinate Z]x[crystal coordinate Z]
 * Y axis is defined based as [Lab Z]x[Lab X]
 */
void n_transformation_matrix_crystal_to_lab(double Q[3][3], double axis[3], double angle)
{
    double normal_lab[3] = {0, 0, 0};
    // double x_ori[3] = {1, 0, 0};
    // double y_ori[3] = {0, 1, 0};
    double z_ori[3] = {0, 0, 1};
    double x_rot[3] = {1, 0, 0};
    double y_rot[3] = {0, 1, 0};
    double z_rot[3] = {0, 0, 1};
    double Q1[3][3] = {0};
    double Q2[3][3] = {0};
    // double z_rot(axis);
    if (!n_vector3_is_parallel(axis, z_ori))
    {
        n_vector3_cross_vector3(x_rot, normal_lab, z_ori);
        n_vector3_cross_vector3(y_rot, z_rot, x_rot);
        n_vector3_normalize_inplace(x_rot);
        n_vector3_normalize_inplace(y_rot);
        n_vector3_normalize_inplace(z_rot);
    }

    n_transformation_matrix_by_coordinate(Q1, x_rot, y_rot, z_rot);
    n_transformation_matrix_axis_angle(Q2, z_rot, angle);
    n_matrix33_multiply_matrix33(Q, Q1, Q2);
}

void n_transformation_matrix_by_tait_bryan(double Q[3][3], double x, double y, double z){
    double x_rot[3] = {1, 0, 0};
    double y_rot[3] = {0, 1, 0};
    double z_rot[3] = {0, 0, 1};
    n_transformation_matrix_axis_angle(Q, x_rot, x);
            // n_matrix33_print("rotation x",Q);

    n_transformation_matrix_axis_angle(Q, y_rot, y);
        // n_matrix33_print("rotation y",Q);

    n_transformation_matrix_axis_angle(Q, z_rot, z);
        // n_matrix33_print("rotation z",Q);

}

void n_transformation_matrix_by_eular(double Q[3][3], double z1, double x, double z2){
    double x_rot[3] = {1, 0, 0};
    double z_rot[3] = {0, 0, 1};
    n_transformation_matrix_axis_angle(Q, z_rot, z1);
    n_transformation_matrix_axis_angle(Q, x_rot, x);
    n_transformation_matrix_axis_angle(Q, z_rot, z2);
}