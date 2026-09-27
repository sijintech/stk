#ifndef __BENCHVARIABLE__
#define __BENCHVARIABLE__
#include <nmathfft/nmathfft.h>

extern int nx,ny,nz,nx21,nx21;
extern double dx,dy,dz,mu0,epon0;
extern double sizescale;

extern int originX, originY, originZ, originIndex;
extern double *epsilonR, epsilonR_homo[6], *Eb;
extern double breakdown_epsilon[6];
extern double *phi;
extern double *Efield;
extern double *possibility;

extern int *treeFlag, *connectFlag;

extern double E_ext[3];
extern double Ez_initial, Ez_slope;
extern char *choice_format[256];

extern NFFT nfft;
extern NPoissonSolverPtr psp;

#endif