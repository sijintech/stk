#include <stdio.h>
#include <stdlib.h>
#include <complex.h>
#include <fftw3-mpi.h>
//#include <fftw3.h>

//Global variable declaration
int x0_3, x1_3, x2_3;
int k0_3, k1_3, k2_3;
int k0_2, k1_2;
int trans_2;

double *inR2C, *outC2R;
fftw_complex *outR2C, *inC2R;
fftw_plan planFWD, planBWD;
double fftwSize3D;

double *inR2C_2, *outC2R_2;
fftw_complex *outR2C_2, *inC2R_2;
fftw_plan planFWD2, planBWD2;
double fftwSize2D;

double *inS, *outS;
double *inT, *outT;
fftw_plan planT, planS;

int x0_3_a, x1_3_a, x2_3_a;
int k0_3_a, k1_3_a, k2_3_a;
int k0_2_a, k1_2_a;
int trans_2_a;

double *inR2C_a, *outC2R_a;
fftw_complex *outR2C_a, *inC2R_a;
fftw_plan planFWD_a, planBWD_a;
double fftwSize3D_a;

double *inR2C_2_a, *outC2R_2_a;
fftw_complex *outR2C_2_a, *inC2R_2_a;
fftw_plan planFWD2_a, planBWD2_a;
double fftwSize2D_a;

double *inS_a, *outS_a;
double *inT_a, *outT_a;
fftw_plan planT_a, planS_a;

//Setup the fourier transform, both forward and backwards.
//This function returns the planning variables and the size variables.
void fftw_setup_3d_mpi_c_(int *Rn0, int *Rn1, int *Rn2, int *Cn0, int *Cn1, int *Cn2, int *lstartR, int *lstart3, int *trans, int *n0, int *n1, int *n2)
{
    int k, m, n, ierr, myid, *recvcounts, size;
    int trans_flag;

    ptrdiff_t local_size, local_n0, local_start;
    ptrdiff_t local_n1, local_1_start;

    //MPI_Initialized(&k);
    MPI_Barrier(MPI_COMM_WORLD);

    fftw_mpi_init();
    MPI_Comm_rank(MPI_COMM_WORLD, &myid);
    //printf("MPI is properly initialized (1/0): %i\n",k);
    MPI_Comm_size(MPI_COMM_WORLD, &size);

    //Setup the 3D Fourier transform
    //Determine the size of the array each processor will handle
    m = (int)(*n2 / 2) + 1;

    //Consider the possibility of not transposing the returned arrays.
    //Determine the size of the transposed array and whether to return a transposed array.
    local_size = fftw_mpi_local_size_3d_transposed(*n0, *n1, *n2 / 2 + 1, MPI_COMM_WORLD, &local_n0, &local_start, &local_n1, &local_1_start);

    //Determine if the transposed data should or should not be used.
    //The transposed data are not used is one of the processors would get no data as a result.
    trans_flag = 1;
    if (local_n1 == 0)
        trans_flag = 0;

    MPI_Reduce(&trans_flag, &trans_2, 1, MPI_INT, MPI_PROD, 0, MPI_COMM_WORLD);
    MPI_Bcast(&trans_2, 1, MPI_INT, 0, MPI_COMM_WORLD);
    *trans = trans_2;

    //Allocate Arrays
    inR2C = (double *)calloc(2 * local_size, sizeof(double));
    outR2C = (fftw_complex *)calloc(local_size , sizeof(fftw_complex));

    inC2R = (fftw_complex *)calloc(local_size , sizeof(fftw_complex));
    outC2R = (double *)calloc(2 * local_size , sizeof(double));

    //Determine the size of the arrays for the 3D transformations
    *Rn0 = local_n0;
    *Rn1 = *n1;
    *Rn2 = *n2;
    x0_3 = local_n0;
    x1_3 = *n1;
    x2_3 = *n2;
    *lstartR = local_start;

    *Cn2 = *n2 / 2 + 1;
    k2_3 = *n2 / 2 + 1;

    //	printf("starting to make plans\n");
    //Plan the forward transforms
    if (trans_2 == 1)
    {
        //Return Transformed data
        planFWD = fftw_mpi_plan_dft_r2c_3d(*n0, *n1, *n2, inR2C, outR2C, MPI_COMM_WORLD, FFTW_MEASURE + FFTW_MPI_TRANSPOSED_OUT);
        planBWD = fftw_mpi_plan_dft_c2r_3d(*n0, *n1, *n2, inC2R, outC2R, MPI_COMM_WORLD, FFTW_MEASURE + FFTW_MPI_TRANSPOSED_IN);
        *Cn0 = local_n1;
        *Cn1 = *n0;
        //The shortened dimension is now in position 3 (i.e. f(*n2,*n0,*n1/2 + 1)). Divided along final dimension
        k0_3 = local_n1;
        k1_3 = *n0;
        *lstart3 = local_1_start;
    }
    else
    {
        //		printf("making non-transposed plans\n");
        //Return data in same layout as it was sent
        planFWD = fftw_mpi_plan_dft_r2c_3d(*n0, *n1, *n2, inR2C, outR2C, MPI_COMM_WORLD, FFTW_MEASURE);
        planBWD = fftw_mpi_plan_dft_c2r_3d(*n0, *n1, *n2, inC2R, outC2R, MPI_COMM_WORLD, FFTW_MEASURE);
        //		printf("made non-transposed plans\n");
        *Cn0 = local_n0;
        *Cn1 = *n1;
        k0_3 = local_n0;
        k1_3 = *n1;
        *lstart3 = local_start;
    }

    fftwSize3D = *n0 * (*n1) * (*n2);
    fftwSize3D = 1 / fftwSize3D;
}

//Program to execute the previously planned foward Fourier transform and return the results.
void fftw_exec_3d_fwd_(int *Cx1, int *Cx2, int *Cx3, double *aR2C, fftw_complex bR2C[*Cx1][*Cx2][*Cx3])
{
    int i, j, k, m;

    //Let's examine the quality of the transcription
    //	printf("the x-size is: %i, %i, %i\n",*Rx1,*Rx2,*Rx3);
    //	printf("the k-size is: %i, %i, %i\n\n",*Cx1,*Cx2,*Cx3);

    //Copy the input array to the array FFTW is expecting to do the transformation with
    for (i = 0; i < x0_3; i++)
    {
        for (j = 0; j < x1_3; j++)
        {
            for (k = 0; k < x2_3; k++)
            {
                inR2C[k + j * (k2_3 * 2) + i * (k2_3 * 2) * (x1_3)] = *(aR2C + k + j * (x2_3) + i * (x2_3) * (x1_3));
            }
        }
    }
    //	j = 18;
    //	k = 48;
    //	for ( i = 0; i< *Rx1;i++ ) {
    //		m = k + j*(*Rx3+2) + i*(*Rx3+2)*(*Rx2);
    //		printf("inR2C[%3i][%3i][%3i] = %9.6f at %6i\n",i,j,k,inR2C[m],m);
    //	}

    //Forward Transform
    fftw_execute(planFWD);

    //Print what's inside the output array.
    //
    //	j = 0;
    //	k = 0;
    //	for ( i = 0; i< *Cx1;i++ ) {
    //		m = k + j*(*Cx3) + i*(*Cx3)*(*Cx2);
    //		printf("outR2C[%3i][%3i][%3i] = (%9.6f,%9.6f)\n",i,j,k,outR2C[m]);
    //	}

    //Copy the output of the Fourier transform to the passed array
    for (i = 0; i < k0_3; i++)
    {
        for (j = 0; j < k1_3; j++)
        {
            for (k = 0; k < k2_3; k++)
            {
                m = 1;
                //outR2C[k + j*(*Cx3) + i*(*Cx3)*(*Cx2)] = m;
                bR2C[i][j][k] = outR2C[k + j * (k2_3) + i * (k2_3) * (k1_3)];
            }
        }
    }

    //exit( );
}

//Program to execute the previously planned backward Fourier transform and return the results.
void fftw_exec_3d_bwd_(int *Rx1, int *Rx2, int *Rx3, fftw_complex *bC2R, double aC2R[*Rx1][*Rx2][*Rx3])
{
    int i, j, k, m;

    //Let's examine the quality of the transcription
    //	printf("the x-size is: %i, %i, %i\n",*Rx1,*Rx2,*Rx3);
    //	printf("the k-size is: %i, %i, %i\n\n",*Cx1,*Cx2,*Cx3);

    //Copy the input array to the array FFTW is expecting to do the transformation with
    //At the same time this unrolls the array into a 1D system FFTW works with more easily
    for (i = 0; i < k0_3; i++)
    {
        for (j = 0; j < k1_3; j++)
        {
            for (k = 0; k < k2_3; k++)
            {
                inC2R[k + j * (k2_3) + i * (k2_3) * (k1_3)] = *(bC2R + k + j * (k2_3) + i * (k2_3) * (k1_3));
            }
        }
    }
    //	j = 1;
    //	k = 0;

    //	for ( i = 0; i< *Cx1;i++ ) {
    //		m = k + j*(*Cx3) + i*(*Cx3)*(*Cx2);
    //		printf("inC2R[%3i][%3i][%3i] = (%11.6f,%11.6f) at %6i\n",i,j,k,inC2R[m],m);
    //	}
    //	printf("\n");

    //Reverse Transform
    fftw_execute(planBWD);

    //Print what's inside the output array.
    //
    //	j = 1;
    //	k = 0;
    //  	for ( i = 0; i< *Rx1;i++ ) {
    //		m = k + j*(*Cx3*2) + i*(*Cx3*2)*(*Rx2);
    //		printf("outC2R[%3i][%3i][%3i] = %9.6f at %6i\n",i,j,k,outC2R[m]*fftwSize3D,m);
    //	}
    //	for (i = 932; i < 1034;i++ ) {
    //		printf("outC2R[%3i] = %9.6f\n",i,outC2R[i]*fftwSize3D);
    //	}

    //Copy the output of the Fourier transform to the passed array
    //This also re-rolls the array into a 3D array that Fortran uses more easily.
    for (i = 0; i < x0_3; i++)
    {
        for (j = 0; j < x1_3; j++)
        {
            for (k = 0; k < x2_3; k++)
            {
                aC2R[i][j][k] = outC2R[k + j * (k2_3 * 2) + i * (k2_3 * 2) * (x1_3)] * fftwSize3D;
            }
        }
    }
}


void fftw_setup_doublesize_3d_mpi_c_(int *Rn0, int *Rn1, int *Rn2, int *Cn0, int *Cn1, int *Cn2, int *lstartR, int *lstart3, int *trans, int *n0, int *n1, int *n2)
{
    int k, m, n, ierr, myid, *recvcounts, size;
    int trans_flag;

    ptrdiff_t local_size, local_n0, local_start;
    ptrdiff_t local_n1, local_1_start;

    //MPI_Initialized(&k);
    MPI_Barrier(MPI_COMM_WORLD);

    fftw_mpi_init();
    MPI_Comm_rank(MPI_COMM_WORLD, &myid);
    //printf("MPI is properly initialized (1/0): %i\n",k);
    MPI_Comm_size(MPI_COMM_WORLD, &size);

 

    //Setup the 3D Fourier transform
    //Determine the size of the array each processor will handle
    m = (int)(*n2 / 2) + 1;

    //Consider the possibility of not transposing the returned arrays.
    //Determine the size of the transposed array and whether to return a transposed array.
    local_size = fftw_mpi_local_size_3d_transposed(*n0, *n1, *n2 / 2 + 1, MPI_COMM_WORLD, &local_n0, &local_start, &local_n1, &local_1_start);

    //Determine if the transposed data should or should not be used.
    //The transposed data are not used is one of the processors would get no data as a result.
    trans_flag = 1;
    if (local_n1 == 0)
        trans_flag = 0;

    MPI_Reduce(&trans_flag, &trans_2_a, 1, MPI_INT, MPI_PROD, 0, MPI_COMM_WORLD);
    MPI_Bcast(&trans_2_a, 1, MPI_INT, 0, MPI_COMM_WORLD);
    *trans = trans_2_a;


    //Allocate Arrays
    inR2C_a = (double *)calloc(2 * local_size , sizeof(double));
    outR2C_a = (fftw_complex *)calloc(local_size , sizeof(fftw_complex));

    inC2R_a = (fftw_complex *)calloc(local_size , sizeof(fftw_complex));
    outC2R_a = (double *)calloc(2 * local_size , sizeof(double));

    //Determine the size of the arrays for the 3D transformations
    *Rn0 = local_n0;
    *Rn1 = *n1;
    *Rn2 = *n2;
    x0_3_a = local_n0;
    x1_3_a = *n1;
    x2_3_a = *n2;
    *lstartR = local_start;

    *Cn2 = *n2 / 2 + 1;
    k2_3_a = *n2 / 2 + 1;

    //	printf("starting to make planS_a\n");
    //Plan the forward transforms
    if (trans_2_a == 1)
    {
        //Return Transformed data
        planFWD_a = fftw_mpi_plan_dft_r2c_3d(*n0, *n1, *n2, inR2C_a, outR2C_a, MPI_COMM_WORLD, FFTW_MEASURE + FFTW_MPI_TRANSPOSED_OUT);
        planBWD_a = fftw_mpi_plan_dft_c2r_3d(*n0, *n1, *n2, inC2R_a, outC2R_a, MPI_COMM_WORLD, FFTW_MEASURE + FFTW_MPI_TRANSPOSED_IN);
        *Cn0 = local_n1;
        *Cn1 = *n0;
        //The shortened dimension is now in position 3 (i.e. f(*n2,*n0,*n1/2 + 1)). Divided along final dimension
        k0_3_a = local_n1;
        k1_3_a = *n0;
        *lstart3 = local_1_start;
    }
    else
    {
        //		printf("making non-transposed planS_a\n");
        //Return data in same layout as it was sent
        planFWD_a = fftw_mpi_plan_dft_r2c_3d(*n0, *n1, *n2, inR2C_a, outR2C_a, MPI_COMM_WORLD, FFTW_MEASURE);
        planBWD_a = fftw_mpi_plan_dft_c2r_3d(*n0, *n1, *n2, inC2R_a, outC2R_a, MPI_COMM_WORLD, FFTW_MEASURE);
        //		printf("made non-transposed planS_a\n");
        *Cn0 = local_n0;
        *Cn1 = *n1;
        k0_3_a = local_n0;
        k1_3_a = *n1;
        *lstart3 = local_start;
    }

    fftwSize3D_a = *n0 * (*n1) * (*n2);
    fftwSize3D_a = 1 / fftwSize3D_a;
}

//Program to execute the previously planned foward Fourier transform and return the results.
void fftw_exec_3d_fwd_doublesize_(int *Cx1, int *Cx2, int *Cx3, double *aR2C, fftw_complex bR2C[*Cx1][*Cx2][*Cx3])
{
    int i, j, k, m;

    //Let's examine the quality of the transcription
    //	printf("the x-size is: %i, %i, %i\n",*Rx1,*Rx2,*Rx3);
    //	printf("the k-size is: %i, %i, %i\n\n",*Cx1,*Cx2,*Cx3);

    //Copy the input array to the array FFTW is expecting to do the transformation with
    for (i = 0; i < x0_3_a; i++)
    {
        for (j = 0; j < x1_3_a; j++)
        {
            for (k = 0; k < x2_3_a; k++)
            {
                inR2C_a[k + j * (k2_3_a * 2) + i * (k2_3_a * 2) * (x1_3_a)] = *(aR2C + k + j * (x2_3_a) + i * (x2_3_a) * (x1_3_a));
            }
        }
    }
    //	j = 18;
    //	k = 48;
    //	for ( i = 0; i< *Rx1;i++ ) {
    //		m = k + j*(*Rx3+2) + i*(*Rx3+2)*(*Rx2);
    //		printf("inR2C_a[%3i][%3i][%3i] = %9.6f at %6i\n",i,j,k,inR2C_a[m],m);
    //	}

    //Forward Transform
    fftw_execute(planFWD_a);

    //Print what's inS_aide the output array.
    //
    //	j = 0;
    //	k = 0;
    //	for ( i = 0; i< *Cx1;i++ ) {
    //		m = k + j*(*Cx3) + i*(*Cx3)*(*Cx2);
    //		printf("outR2C_a[%3i][%3i][%3i] = (%9.6f,%9.6f)\n",i,j,k,outR2C_a[m]);
    //	}

    //Copy the output of the Fourier transform to the passed array
    for (i = 0; i < k0_3_a; i++)
    {
        for (j = 0; j < k1_3_a; j++)
        {
            for (k = 0; k < k2_3_a; k++)
            {
                m = 1;
                //outR2C_a[k + j*(*Cx3) + i*(*Cx3)*(*Cx2)] = m;
                bR2C[i][j][k] = outR2C_a[k + j * (k2_3_a) + i * (k2_3_a) * (k1_3_a)];
            }
        }
    }

    //exit( );
}

//Program to execute the previously planned backward Fourier transform and return the results.
void fftw_exec_3d_bwd_doublesize_(int *Rx1, int *Rx2, int *Rx3, fftw_complex *bC2R, double aC2R[*Rx1][*Rx2][*Rx3])
{
    int i, j, k, m;

    //Let's examine the quality of the transcription
    //	printf("the x-size is: %i, %i, %i\n",*Rx1,*Rx2,*Rx3);
    //	printf("the k-size is: %i, %i, %i\n\n",*Cx1,*Cx2,*Cx3);

    //Copy the input array to the array FFTW is expecting to do the transformation with
    //At the same time this unrolls the array into a 1D system FFTW works with more easily
    for (i = 0; i < k0_3_a; i++)
    {
        for (j = 0; j < k1_3_a; j++)
        {
            for (k = 0; k < k2_3_a; k++)
            {
                inC2R_a[k + j * (k2_3_a) + i * (k2_3_a) * (k1_3_a)] = *(bC2R + k + j * (k2_3_a) + i * (k2_3_a) * (k1_3_a));
            }
        }
    }
    //	j = 1;
    //	k = 0;

    //	for ( i = 0; i< *Cx1;i++ ) {
    //		m = k + j*(*Cx3) + i*(*Cx3)*(*Cx2);
    //		printf("inC2R_a[%3i][%3i][%3i] = (%11.6f,%11.6f) at %6i\n",i,j,k,inC2R_a[m],m);
    //	}
    //	printf("\n");

    //Reverse Transform
    fftw_execute(planBWD_a);

    //Print what's inS_aide the output array.
    //
    //	j = 1;
    //	k = 0;
    //  	for ( i = 0; i< *Rx1;i++ ) {
    //		m = k + j*(*Cx3*2) + i*(*Cx3*2)*(*Rx2);
    //		printf("outC2R_a[%3i][%3i][%3i] = %9.6f at %6i\n",i,j,k,outC2R_a[m]*fftwSize3D_a,m);
    //	}
    //	for (i = 932; i < 1034;i++ ) {
    //		printf("outC2R_a[%3i] = %9.6f\n",i,outC2R_a[i]*fftwSize3D_a);
    //	}

    //Copy the output of the Fourier transform to the passed array
    //This also re-rolls the array into a 3D array that Fortran uses more easily.
    for (i = 0; i < x0_3_a; i++)
    {
        for (j = 0; j < x1_3_a; j++)
        {
            for (k = 0; k < x2_3_a; k++)
            {
                aC2R[i][j][k] = outC2R_a[k + j * (k2_3_a * 2) + i * (k2_3_a * 2) * (x1_3_a)] * fftwSize3D_a;
            }
        }
    }
}




//Setup the fourier transform, both forward and backwards.
//This function returns the planning variables and the size variables.
void fftw_setup_2d_mpi_c_(int *Hn0, int *Hn1, int *lstart2, int *n0, int *n1)
{
    int k, m, n, ierr, myid, *recvcounts, size;
    int trans_flag;

    ptrdiff_t local_size, local_n0, local_start;
    ptrdiff_t local_n1, local_1_start;

    //MPI_Initialized(&k);
    MPI_Barrier(MPI_COMM_WORLD);

    // fftw_mpi_init();
    MPI_Comm_rank(MPI_COMM_WORLD, &myid);
    //printf("MPI is properly initialized (1/0): %i\n",k);
    MPI_Comm_size(MPI_COMM_WORLD, &size);

    //Setup the 2D transformation.

    //Consider the possibility of not transposing the returned arrays.
    //Determine the size of the transposed array and whether to return a transposed array.
    local_size = fftw_mpi_local_size_2d_transposed(*n0, *n1 / 2 + 1, MPI_COMM_WORLD, &local_n0, &local_start, &local_n1, &local_1_start);
    //	MPI_Barrier(MPI_COMM_WORLD);

    //	if (myid == 0)
    //		printf("INFORMATION ON 2D TRANSFORMS!\n\n");
    //
    //	MPI_Barrier(MPI_COMM_WORLD);
    //	for(k = 0; k< size;k++) {
    //		if (myid == k) {
    //		printf("local 0 start on processor %2i: %d\n",myid,local_start);
    //		printf("local 0 size on processor  %2i: %d\n",myid,local_n0);
    //		printf("local 1 start on processor %2i: %d\n",myid,local_1_start);
    //		printf("local 1 size on processor  %2i: %d\n",myid,local_n1);
    //		printf("Transposed data from %2i (0/1): %i\n",myid,trans_2);
    //		printf("local entries on processor %2i: %d\n\n",myid,local_size);
    //		MPI_Barrier(MPI_COMM_WORLD);
    //		}
    //	}
    //
    //	MPI_Barrier(MPI_COMM_WORLD);
    //	if (myid == 0) {
    //		printf("END 2D FOURIER INFORMATION\n\n");
    //	}

    //	MPI_Barrier(MPI_COMM_WORLD);

    //Allocate Arrays

    inR2C_2 = (double *)calloc(2 * local_size , sizeof(double));
    outR2C_2 = (fftw_complex *)calloc(local_size , sizeof(fftw_complex));

    inC2R_2 = (fftw_complex *)calloc(local_size , sizeof(fftw_complex));
    outC2R_2 = (double *)calloc(2 * local_size , sizeof(double));

    //Determine the size of the arrays for the 2D transformations
    //Actually, these arrays are identical in extent to Rn0 and Rn1

    //Plan the forward transforms (that does not return transposed data!)
    //Return data in recieved layout
    planFWD2 = fftw_mpi_plan_dft_r2c_2d(*n0, *n1, inR2C_2, outR2C_2, MPI_COMM_WORLD, FFTW_MEASURE);
    planBWD2 = fftw_mpi_plan_dft_c2r_2d(*n0, *n1, inC2R_2, outC2R_2, MPI_COMM_WORLD, FFTW_MEASURE);
    *Hn0 = local_n0;
    *Hn1 = *n1 / 2 + 1;
    //The shortened dimension is now in position 2 (i.e. f(*n0,*n1/2 + 1)). Divided along first dimension
    //In FFTW the padded real array must have dimensions of f(*n0,2(*n1/2+1))
    k0_2 = local_n0;
    k1_2 = (*n1 / 2 + 1);
    *lstart2 = local_start;

    //Fourier Transform normalizing constant
    fftwSize2D = (*n0 * (*n1));
    fftwSize2D = 1 / fftwSize2D;
    //	MPI_Barrier(MPI_COMM_WORLD);

    //	if(myid == 0)
    //		printf("fftwSize2D: %11.6f\n",fftwSize2D);
    //
    //	MPI_Barrier(MPI_COMM_WORLD);
}

//Program to execute the previously planned foward Fourier transform in 2D and return the results.
void fftw_exec_2d_fwd_(int *Hn1, int *Hn2, int *Rn3, double *aR2C, fftw_complex bR2C[*Hn1][*Hn2][*Rn3])
{
    int i, j, k, m;
    //int myid,size;
    int p;

    //Let's examine the quality of the transcription
    //	printf("the x-size is: %i, %i, %i\n",*Rx1,*Rx2,*Rx3);
    //	printf("the k-size is: %i, %i, %i\n\n",*Cx1,*Cx2,*Cx3);
    //	printf("k1_2 = %d\nk0_2 = %d\n\n",k1_2,k0_2);

    //MPI_Comm_rank(MPI_COMM_WORLD,&myid);
    //MPI_Comm_size(MPI_COMM_WORLD, &size);

    //The routine will transform the number of layers passed to the routine
    for (k = 0; k < *Rn3; k++)
    {

        //Copy the input array to the array FFTW is expecting to do the transformation with
        for (i = 0; i < x0_3; i++)
        {
            for (j = 0; j < x1_3; j++)
            {
                inR2C_2[j + i * (k1_2 * 2)] = *(aR2C + k + j * (*Rn3) + i * (*Rn3) * (x1_3));
            }
        }

        //		if(k==0) {
        //		j = 0;
        //		for(m=0;m<size;m++) {
        //			if(myid == m) {
        //				for(i=0;i<x0_3;i++) {
        //					p = j + i*k1_2*2;
        //					printf("(%2i) inR2C_2 at (%3i,%3i) %4i: %9.6f\n",myid,i,j,p,inR2C_2[p]);
        //				}
        //			}
        //			MPI_Barrier(MPI_COMM_WORLD);
        //		}
        //		printf("Hello World\n");
        //		}

        //Forward Transform
        fftw_execute(planFWD2);

        //Copy the output of the Fourier transform to the passed array
        for (i = 0; i < k0_2; i++)
        {
            for (j = 0; j < k1_2; j++)
            {
                bR2C[i][j][k] = outR2C_2[j + i * (k1_2)];
            }
        }
        //		if(k==0) {
        //		j = 0;
        //		for(m=0;m<size;m++) {
        //			if(myid == m) {
        //				for(i=0;i<k0_2;i++) {
        //					p = j + i*k1_2;
        //					printf("(%2i) outR2C_2 at (%3i,%3i) %4i: (%11.4f,%11.4f)\n",myid,i,j,j + i*k1_2,outR2C_2[p]);
        //				}
        //			}
        //			MPI_Barrier(MPI_COMM_WORLD);
        //		}
        //
        //		MPI_Barrier(MPI_COMM_WORLD);
        //		}
    }

    //exit( );
}

//Program to execute the previously planned backward Fourier transform in 2D and return the results.
void fftw_exec_2d_bwd_(int *Rn1, int *Rn2, int *Rn3, fftw_complex *bC2R, double aC2R[*Rn1][*Rn2][*Rn3])
{
    int i, j, k, m;

    //Let's examine the quality of the transcription
    //	printf("the x-size is: %i, %i, %i\n",*Rx1,*Rx2,*Rx3);
    //	printf("the k-size is: %i, %i, %i\n\n",*Cx1,*Cx2,*Cx3);
    //	printf("k1_2 = %d\nk0_2 = %d\n\n",k1_2,k0_2);
    m = k1_2 * 2;

    for (k = 0; k < *Rn3; k++)
    {

        //Copy the input array to the array FFTW is expecting to do the transformation with
        for (i = 0; i < k0_2; i++)
        {
            for (j = 0; j < k1_2; j++)
            {
                inC2R_2[j + i * k1_2] = *(bC2R + k + j * (*Rn3) + i * (*Rn3) * (k1_2));
            }
        }

        //Forward Transform
        fftw_execute(planBWD2);

        //Copy the output of the Fourier transform to the passed array
        for (i = 0; i < x0_3; i++)
        {
            for (j = 0; j < x1_3; j++)
            {
                aC2R[i][j][k] = outC2R_2[j + i * (m)] * fftwSize2D;
            }
        }
    }
}


void fftw_setup_doublesize_2d_mpi_c_(int *Hn0, int *Hn1, int *lstart2, int *n0, int *n1)
{
    int k, m, n, ierr, myid, *recvcounts, size;
    int trans_flag;

    ptrdiff_t local_size, local_n0, local_start;
    ptrdiff_t local_n1, local_1_start;

    //MPI_Initialized(&k);
    MPI_Barrier(MPI_COMM_WORLD);

    fftw_mpi_init();
    MPI_Comm_rank(MPI_COMM_WORLD, &myid);
    //printf("MPI is properly initialized (1/0): %i\n",k);
    MPI_Comm_size(MPI_COMM_WORLD, &size);

    //Setup the 2D transformation.

    //Consider the possibility of not transposing the returned arrays.
    //Determine the size of the transposed array and whether to return a transposed array.
    local_size = fftw_mpi_local_size_2d_transposed(*n0, *n1 / 2 + 1, MPI_COMM_WORLD, &local_n0, &local_start, &local_n1, &local_1_start);


    //Allocate Arrays

    inR2C_2_a = (double *)calloc(2 * local_size , sizeof(double));
    outR2C_2_a = (fftw_complex *)calloc(local_size , sizeof(fftw_complex));

    inC2R_2_a = (fftw_complex *)calloc(local_size , sizeof(fftw_complex));
    outC2R_2_a = (double *)calloc(2 * local_size , sizeof(double));

    //Determine the size of the arrays for the 2D transformations
    //Actually, these arrays are identical in extent to Rn0 and Rn1

    //Plan the forward transforms (that does not return transposed data!)
    //Return data in recieved layout
    planFWD2_a = fftw_mpi_plan_dft_r2c_2d(*n0, *n1, inR2C_2_a, outR2C_2_a, MPI_COMM_WORLD, FFTW_MEASURE);
    planBWD2_a = fftw_mpi_plan_dft_c2r_2d(*n0, *n1, inC2R_2_a, outC2R_2_a, MPI_COMM_WORLD, FFTW_MEASURE);
    *Hn0 = local_n0;
    *Hn1 = *n1 / 2 + 1;
    //The shortened dimension is now in position 2 (i.e. f(*n0,*n1/2 + 1)). Divided along first dimension
    //In FFTW the padded real array must have dimensions of f(*n0,2(*n1/2+1))
    k0_2_a = local_n0;
    k1_2_a = (*n1 / 2 + 1);
    *lstart2 = local_start;

    //Fourier Transform normalizing constant
    fftwSize2D_a = (*n0 * (*n1));
    fftwSize2D_a = 1 / fftwSize2D_a;
    //	MPI_Barrier(MPI_COMM_WORLD);

    //	if(myid == 0)
    //		printf("fftwSize2D_a: %11.6f\n",fftwSize2D_a);
    //
    //	MPI_Barrier(MPI_COMM_WORLD);

}


//Program to execute the previously planned foward Fourier transform in 2D and return the results.
void fftw_exec_2d_fwd_doublesize_c_(int *Hn1, int *Hn2, int *Rn3, double *aR2C, fftw_complex bR2C[*Hn1][*Hn2][*Rn3])
{
    int i, j, k, m;
    //int myid,size;
    int p;

    //Let's examine the quality of the transcription
    //	printf("the x-size is: %i, %i, %i\n",*Rx1,*Rx2,*Rx3);
    //	printf("the k-size is: %i, %i, %i\n\n",*Cx1,*Cx2,*Cx3);
    //	printf("k1_2_a = %d\nk0_2_a = %d\n\n",k1_2_a,k0_2_a);

    //MPI_Comm_rank(MPI_COMM_WORLD,&myid);
    //MPI_Comm_size(MPI_COMM_WORLD, &size);

    //The routine will transform the number of layers passed to the routine
    for (k = 0; k < *Rn3; k++)
    {

        //Copy the input array to the array FFTW is expecting to do the transformation with
        for (i = 0; i < x0_3_a; i++)
        {
            for (j = 0; j < x1_3_a; j++)
            {
                inR2C_2_a[j + i * (k1_2_a * 2)] = *(aR2C + k + j * (*Rn3) + i * (*Rn3) * (x1_3_a));
            }
        }

        //		if(k==0) {
        //		j = 0;
        //		for(m=0;m<size;m++) {
        //			if(myid == m) {
        //				for(i=0;i<x0_3_a;i++) {
        //					p = j + i*k1_2_a*2;
        //					printf("(%2i) inR2C_2_a at (%3i,%3i) %4i: %9.6f\n",myid,i,j,p,inR2C_2_a[p]);
        //				}
        //			}
        //			MPI_Barrier(MPI_COMM_WORLD);
        //		}
        //		printf("Hello World\n");
        //		}

        //Forward Transform
        fftw_execute(planFWD2_a);

        //Copy the output of the Fourier transform to the passed array
        for (i = 0; i < k0_2_a; i++)
        {
            for (j = 0; j < k1_2_a; j++)
            {
                bR2C[i][j][k] = outR2C_2_a[j + i * (k1_2_a)];
            }
        }
        //		if(k==0) {
        //		j = 0;
        //		for(m=0;m<size;m++) {
        //			if(myid == m) {
        //				for(i=0;i<k0_2_a;i++) {
        //					p = j + i*k1_2_a;
        //					printf("(%2i) outR2C_2_a at (%3i,%3i) %4i: (%11.4f,%11.4f)\n",myid,i,j,j + i*k1_2_a,outR2C_2_a[p]);
        //				}
        //			}
        //			MPI_Barrier(MPI_COMM_WORLD);
        //		}
        //
        //		MPI_Barrier(MPI_COMM_WORLD);
        //		}
    }

    //exit( );
}

//Program to execute the previously planned backward Fourier transform in 2D and return the results.
void fftw_exec_2d_bwd_doublesize_(int *Rn1, int *Rn2, int *Rn3, fftw_complex *bC2R, double aC2R[*Rn1][*Rn2][*Rn3])
{
    int i, j, k, m;

    //Let's examine the quality of the transcription
    //	printf("the x-size is: %i, %i, %i\n",*Rx1,*Rx2,*Rx3);
    //	printf("the k-size is: %i, %i, %i\n\n",*Cx1,*Cx2,*Cx3);
    //	printf("k1_2_a = %d\nk0_2_a = %d\n\n",k1_2_a,k0_2_a);
    m = k1_2_a * 2;

    for (k = 0; k < *Rn3; k++)
    {

        //Copy the input array to the array FFTW is expecting to do the transformation with
        for (i = 0; i < k0_2_a; i++)
        {
            for (j = 0; j < k1_2_a; j++)
            {
                inC2R_2_a[j + i * k1_2_a] = *(bC2R + k + j * (*Rn3) + i * (*Rn3) * (k1_2_a));
            }
        }

        //Forward Transform
        fftw_execute(planBWD2_a);

        //Copy the output of the Fourier transform to the passed array
        for (i = 0; i < x0_3_a; i++)
        {
            for (j = 0; j < x1_3_a; j++)
            {
                aC2R[i][j][k] = outC2R_2_a[j + i * (m)] * fftwSize2D_a;
            }
        }
    }
}