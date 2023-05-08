find_package(MPI REQUIRED)

if(NOT TARGET MPI::MPI_Fortran)
    add_library(MPI::MPI_Fortran IMPORTED INTERFACE)

    set_property(TARGET MPI::MPI_Fortran
                 PROPERTY INTERFACE_COMPILE_OPTIONS ${MPI_Fortran_COMPILE_FLAGS})
    set_property(TARGET MPI::MPI_Fortran
                 PROPERTY INTERFACE_INCLUDE_DIRECTORIES "${MPI_Fortran_INCLUDE_PATH}")
    set_property(TARGET MPI::MPI_Fortran
                 PROPERTY INTERFACE_LINK_LIBRARIES ${MPI_Fortran_LINK_FLAGS} ${MPI_Fortran_LIBRARIES})
endif()

