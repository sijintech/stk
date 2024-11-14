submodule(array_operation_mpi) max_array
contains

module subroutine maxArray4(maxima, array, flagAbs)
    use nmathbasic
    use fft_3D_mpi
    implicit none
    real(kind=rdp), intent(out) :: maxima
    real(kind=rdp), dimension(:, :, :, :), intent(in) :: array
    logical, intent(in) :: flagAbs
    real(kind=rdp) :: hold

    if (flagAbs) then
        hold = MAXVAL(abs(array))
    else
        hold = MAXVAL(array)
    endif

    call MPI_Barrier(MPI_Comm_World, ierr)
    call MPI_AllReduce(hold, maxima, 1, MPI_Real8, MPI_MAX, MPI_COMM_WORLD, ierr)
end subroutine maxArray4

module subroutine maxArray3(maxima, array, flagAbs)
    use nmathbasic
    use fft_3D_mpi
    implicit none
    real(kind=rdp), intent(out) :: maxima
    real(kind=rdp), dimension(:, :, :), intent(in) :: array
    logical, intent(in) :: flagAbs
    real(kind=rdp) :: hold

    if (flagAbs) then
        hold = MAXVAL(abs(array))
    else
        hold = MAXVAL(array)
    endif

    call MPI_Barrier(MPI_Comm_World, ierr)
    call MPI_AllReduce(hold, maxima, 1, MPI_Real8, MPI_MAX, MPI_COMM_WORLD, ierr)
end subroutine maxArray3

end submodule max_array
