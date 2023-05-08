
if(${CMAKE_SYSTEM_NAME} MATCHES "Windows" )
set(FFTW_PATH "C:\\Program Files\\fftw")
set(FFTW_INCLUDE ${FFTW_PATH} CACHE STRING "set the include directory for fftw_mpi")
set(FFTW_LIB ${FFTW_PATH} CACHE STRING "set the lib directory for fftw_mpi")
else()

if (${CMAKE_SYSTEM_NAME} MATCHES "Darwin")
set(FFTW_PATH "/usr/local")
else()
set(FFTW_PATH "/opt/fftw-gcc")
endif()
set(FFTW_INCLUDE ${FFTW_PATH}/include CACHE STRING "set the include directory for fftw_mpi")
set(FFTW_LIB ${FFTW_PATH}/lib CACHE STRING "set the lib directory for fftw_mpi")

endif()

