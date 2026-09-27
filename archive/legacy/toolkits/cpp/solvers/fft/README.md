#math-fft
migration from gitee nmath-fft 3624229433859a711b04f9ec960b0fbb064bd2a9 2021 Jun 18 14:17:34


Since the size of reciprocal space is fixed after initialization, we can pass the the first address of 3D array to n_fft_data_get and copy the data from 1D kx array into the 3D array.


# Working on mac
export LIBRARY_PATH=/Library/Developer/CommandLineTools/SDKs/MacOSX11.1.sdk/usr/lib/

source /opt/intel/oneapi/setvars.sh
CC=icc CXX=icpc FC=ifort cmake -DCMAKE_VERBOSE_MAKEFILE=TRUE ..