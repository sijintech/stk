#io-basic

From gitee nio-basic 9b5b82272e5059622d21c8a83d52ae863abb0792 2021 Aug 6 16:54

export LIBRARY_PATH=/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk/usr/lib:/usr/local/Cellar/gcc/10.2.0/lib/gcc/10

source /opt/intel/oneapi/setvars.sh
CC=icc CXX=icpc FC=ifort cmake -DCMAKE_VERBOSE_MAKEFILE=TRUE ..
