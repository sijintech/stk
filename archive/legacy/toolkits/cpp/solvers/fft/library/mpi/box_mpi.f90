submodule(array_operation_mpi) box_mpi

contains

module subroutine sumBox(total, array, box)
    use nmathbasic
    ! use mod_fftw_mpi
    ! use simsize
    use fft_3D_mpi
    implicit none
    real(kind=rdp), dimension(:, :, :), intent(in) :: array
    real(kind=rdp), intent(out) :: total
    integer, dimension(6), optional, intent(in) :: box
    real(kind=rdp) :: hold
    integer :: xmin, xmax, ymin, ymax, zmin, zmax

    if (present(box)) then
        xmin = box(1)
        xmax = box(2)
        ymin = box(3)
        ymax = box(4)
        zmin = box(5)
        zmax = box(6)
        if (lstartR >= xmin) then
            xmin = 1
        else
            xmin = xmin - lstartR
        endif
        if (Rn1 + lstartR <= xmax) then
            xmax = Rn1
        else
            xmax = xmax - lstartR
        endif

    else
        xmin = 1
        xmax = Rn1
        ymin = 1
        ymax = Rn2
        zmin = k1
        zmax = k2

    endif

    hold = sum(array(zmin:zmax, ymin:ymax, xmin:xmax))
    call MPI_Barrier(MPI_Comm_World, ierr)
    call MPI_Reduce(hold, total, 1, MPI_Real8, MPI_SUM, 0, MPI_COMM_WORLD, ierr)
end subroutine

module subroutine avgBox(avg, array, flagAbs, box)
    use nmathbasic
    use fft_3D_mpi
    ! use mod_fftw_mpi
    ! use simsize
    implicit none
    real(kind=rdp), intent(out) :: avg
    real(kind=rdp), dimension(:, :, :), intent(in) :: array
    logical, intent(in) :: flagAbs
    integer, dimension(6), optional, intent(in) :: box
    real(kind=rdp) :: hold, total
    integer :: xmin, xmax, ymin, ymax, zmin, zmax, ntotal

    if (present(box)) then
        xmin = box(1)
        xmax = box(2)
        ymin = box(3)
        ymax = box(4)
        zmin = box(5)
        zmax = box(6)
        if (lstartR >= xmin) then
            xmin = 1
        else
            xmin = xmin - lstartR
        endif
        if (Rn1 + lstartR <= xmax) then
            xmax = Rn1
        else
            xmax = xmax - lstartR
        endif

    else
        xmin = 1
        xmax = Rn1
        ymin = 1
        ymax = Rn2
        zmin = k1
        zmax = k2
    endif

    ntotal = (xmax - xmin + 1)*(ymax - ymin + 1)*(zmax - zmin + 1)

    if (flagAbs) then
        hold = sum(abs(array(zmin:zmax, ymin:ymax, xmin:xmax)))
    else
        hold = sum(array(zmin:zmax, ymin:ymax, xmin:xmax))
    endif

    call MPI_Barrier(MPI_Comm_World, ierr)
    call MPI_AllReduce(hold, total, 1, MPI_Real8, MPI_SUM, MPI_COMM_WORLD, ierr)
    avg = total/ntotal/process
end subroutine

module subroutine minBox(minima, array, flagAbs, box)
    use nmathbasic
    use fft_3D_mpi
    ! use mod_fftw_mpi
    ! use simsize
    implicit none
    real(kind=rdp), intent(out) :: minima
    real(kind=rdp), dimension(:, :, :), intent(in) :: array
    integer, dimension(6), optional, intent(in) :: box
    logical, intent(in) :: flagAbs
    real(kind=rdp) :: hold
    integer :: xmin, xmax, ymin, ymax, zmin, zmax

    if (present(box)) then
        xmin = box(1)
        xmax = box(2)
        ymin = box(3)
        ymax = box(4)
        zmin = box(5)
        zmax = box(6)
        if (lstartR >= xmin) then
            xmin = 1
        else
            xmin = xmin - lstartR
        endif
        if (Rn1 + lstartR <= xmax) then
            xmax = Rn1
        else
            xmax = xmax - lstartR
        endif

    else
        xmin = 1
        xmax = Rn1
        ymin = 1
        ymax = Rn2
        zmin = k1
        zmax = k2
    endif

    if (flagAbs) then
        hold = MINVAL(abs(array(zmin:zmax, ymin:ymax, xmin:xmax)))
    else
        hold = MINVAL(array(zmin:zmax, ymin:ymax, xmin:xmax))
    endif

    call MPI_Barrier(MPI_Comm_World, ierr)
    call MPI_AllReduce(hold, minima, 1, MPI_Real8, MPI_MIN, MPI_COMM_WORLD, ierr)
endsubroutine

module subroutine maxBox(maxima, array, flagAbs, box)
    use nmathbasic
    use fft_3D_mpi
    ! use mod_fftw_mpi
    ! use simsize
    implicit none
    real(kind=rdp), intent(out) :: maxima
    real(kind=rdp), dimension(:, :, :), intent(in) :: array
    integer, dimension(6), optional, intent(in) :: box
    logical, intent(in) :: flagAbs
    real(kind=rdp) :: hold
    integer :: xmin, xmax, ymin, ymax, zmin, zmax

    if (present(box)) then
        xmin = box(1)
        xmax = box(2)
        ymin = box(3)
        ymax = box(4)
        zmin = box(5)
        zmax = box(6)
        if (lstartR >= xmin) then
            xmin = 1
        else
            xmin = xmin - lstartR
        endif
        if (Rn1 + lstartR <= xmax) then
            xmax = Rn1
        else
            xmax = xmax - lstartR
        endif

    else
        xmin = 1
        xmax = Rn1
        ymin = 1
        ymax = Rn2
        zmin = k1
        zmax = k2
    endif

    if (flagAbs) then
        hold = MAXVAL(abs(array(zmin:zmax, ymin:ymax, xmin:xmax)))
    else
        hold = MAXVAL(array(zmin:zmax, ymin:ymax, xmin:xmax))
    endif

    call MPI_Barrier(MPI_Comm_World, ierr)
    call MPI_AllReduce(hold, maxima, 1, MPI_Real8, MPI_MAX, MPI_COMM_WORLD, ierr)
endsubroutine

end submodule
