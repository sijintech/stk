submodule(public_fft_3D_mpi) fftw_3D_mpi
use fft_3D_mpi
use, intrinsic :: iso_C_binding
implicit none
contains
 !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

module subroutine fftw_setup_3D_mpi(dims, ddims, R, C, lstart, trans, Rn1All_out, lstartRAll_out)

    ! use simSize
    ! use mod_fftw_mpi
    ! use print_utilities
    ! use license

    use, intrinsic :: iso_C_binding

    implicit none

    integer, intent(IN), dimension(3) :: dims
    real(kind=rdp), intent(IN), dimension(3) :: ddims
    integer, intent(OUT)::R(3), C(3), lstart(3), trans
    integer, intent(OUT), optional :: Rn1All_out(0:), lstartRAll_out(0:)
    integer i, j, k, n
    logical init_flag
    real(kind=rdp) twopi, fk1
    integer trans_doubleSize   !tuy02
    character(len=78) :: text1

    twopi = 4.d0*atan(1.d0)*2.0
    nx = dims(1); ny = dims(2); nz = dims(3)
    dx = ddims(1); dy = ddims(2); dz = ddims(3); 
    !Check if MPI is currently initialized.  If not, initalize it.
    call MPI_INITIALIZED(init_flag, ierr)
    if (.not. init_flag) call MPI_INIT(ierr)

    ! print *, 'In_fftw_setup',rank
    call MPI_Barrier(MPI_COMM_WORLD, ierr)
    call mpi_comm_rank(mpi_comm_world, rank, ierr)
    call mpi_comm_size(mpi_comm_world, process, ierr)

!    if(.not.valid) then
!        call MPI_Finalize(ierr)
!        stop
!    endif

    ! print *, 'In_fftw_setup after rank common',rank
    !Check that nx != 1.  No quasi 2D simulations are allowed with the MPI interface.
    ! Rather, the arrays MUST be padded to size 2 in the y-direction
    if (ny .eq. 1 .and. process .gt. 1) then
        if (rank .eq. 0) then
            print *, '**************************************************************'
            print *, 'Error: ny = 1 detected.'
            print *, '       Quasi 2D simulations are not allowed with MPI interface'
            print *, '       Attempting recovery by padding to ny = 2!'
            print *, '**************************************************************'
            !'
        endif
        ny = 2
    endif

    call MPI_Barrier(MPI_COMM_WORLD, ierr)
    call fftw_setup_3D_mpi_c(Rn1, Rn2, Rn3, Cn1, Cn2, Cn3, lstartR, lstart3, trans, nx, ny, nz)

    !Prepare the system size for output to the calling routine
    R(1) = Rn1; R(2) = Rn2; R(3) = Rn3
    C(1) = Cn1; C(2) = Cn2; C(3) = Cn3
    lstart(1) = lstartR; lstart(3) = lstart3

    !List of system size of each process is then collected and broadcasted to all processes   !tuy20160531b
    allocate (Rn1All(0:process - 1)); Rn1All = 0.
    allocate (lstartRAll(0:process - 1)); lstartRAll = 0.

    Rn1All(rank) = Rn1
    lstartRAll(rank) = lstartR
    call MPI_Barrier(MPI_Comm_world, ierr)

    do n = 0, process - 1
        call MPI_Bcast(Rn1All(n), 1, MPI_integer, n, MPI_Comm_World, ierr)
        call MPI_Bcast(lstartRAll(n), 1, MPI_integer, n, MPI_Comm_World, ierr)
    enddo
    call MPI_Barrier(MPI_Comm_world, ierr)   !tuy20160531f

    if (present(Rn1All_out)) Rn1All_out(0:process - 1) = Rn1All(0:process - 1)
    if (present(lstartRAll_out)) lstartRAll_out(0:process - 1) = lstartRAll(0:process - 1)

8001 format('Real simulation size (3D) on    ', i2, ' is ', 3i5)
8002 format('Complex simulation size (3D) on ', i2, ' is ', 3i5)
8003 format('Starting real value (3D/2D) on  ', i2, ' is ', i5)
8004 format('Starting complex value (3D) on  ', i2, ' is ', i5)

    call MPI_BARRIER(MPI_COMM_WORLD, ierr)
    do i = 0, process - 1
        call MPI_BARRIER(MPI_COMM_WORLD, ierr)
        if (rank .eq. i) then
            ! write (text1, 8001) rank, Rn1, Rn2, Rn3
            ! call printMessage(text1, ' ', 'l')
            ! write (text1, 8002) rank, Cn1, Cn2, Cn3
            ! call printMessage(text1, ' ', 'l')
            ! write (text1, 8003) rank, lstartR
            ! call printMessage(text1, ' ', 'l')
            ! write (text1, 8004) rank, lstart3
            ! call printMessage(text1, ' ', 'l')
            ! call printMessage("", '-', 'l')

     write(*,8001) rank,Rn1,Rn2,Rn3
     write(*,8002) rank,Cn1,Cn2,Cn3
     write(*,8003) rank,lstartR
     write(*,8004) rank,lstart3
!      write(*,8005) rank,Rn1,Rn2
!      write(*,8006) rank,Hn1,Hn2
!      write(*,8007) rank,lstart2

        endif
        call MPI_BARRIER(MPI_COMM_WORLD, ierr)
    enddo

    allocate (mqk1_3(Cn3, Cn2, Cn1))
    allocate (mqk2_3(Cn3, Cn2, Cn1))
    allocate (mqk3_3(Cn3, Cn2, Cn1))
    !print *, 'Finished allocating'

    !Define the 3D k-vectors
    do i = 1, Cn3
        do j = 1, Cn2
            do k = 1, Cn1
                !kx-vectors
                fk1 = float(lstart3 + k - 1)
                if (trans .eq. 1) fk1 = float(j - 1)
                if (fk1 .ge. float(nx)/2) fk1 = fk1 - float(nx)
                mqk1_3(i, j, k) = twopi*fk1/(dx*float(nx))

                !ky-vectors
                fk1 = float(j - 1)
                if (trans .eq. 1) fk1 = float(lstart3 + k - 1)
                if (fk1 .ge. float(ny)/2) fk1 = fk1 - float(ny)
                mqk2_3(i, j, k) = twopi*fk1/(dy*float(ny))

                !kz-vectors
                fk1 = float(i - 1)
                if (fk1 .ge. float(nz)/2) fk1 = fk1 - float(nz)
                mqk3_3(i, j, k) = twopi*fk1/(dz*float(nz))
            enddo
        enddo
    enddo

end subroutine

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
module subroutine forward_mpi(fwd, fwdk)

    ! use mod_fftw_mpi
    !use mod_interfaces

    implicit none
    real(kind=rdp), intent(in) :: fwd(:, :, :)
    complex(kind=cdp), intent(out) :: fwdk(:, :, :)

    call fftw_exec_3d_fwd(Cn1, Cn2, Cn3, fwd, fwdk)

end subroutine

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
module subroutine backward_mpi(fwdk, fwd)

    ! use mod_fftw_mpi
    !use mod_interfaces

    implicit none
    complex(kind=cdp), intent(in) :: fwdk(:, :, :)
    real(kind=rdp), intent(out) :: fwd(:, :, :)

    call fftw_exec_3d_bwd(Rn1, Rn2, Rn3, fwdk, fwd)

end subroutine

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

module subroutine fftw_setup_doubleSize_3D_mpi()

    ! use simSize
    ! use mod_fftw_mpi
    ! use print_utilities
    ! use license

    use, intrinsic :: iso_C_binding

    implicit none

    integer i, j, k, n
    logical init_flag
    real(kind=rdp) twopi, fk1
    integer trans_doubleSize   !tuy02
    character(len=78) :: text1

    twopi = 4.d0*atan(1.d0)*2.0
    ! nx = dims(1); ny = dims(2); nz = dims(3)
    ! dx = ddims(1); dy = ddims(2); dz = ddims(3);
    !Check if MPI is currently initialized.  If not, initalize it.
    call MPI_INITIALIZED(init_flag, ierr)
    if (.not. init_flag) call MPI_INIT(ierr)

    ! print *, 'In_fftw_setup',rank
    call MPI_Barrier(MPI_COMM_WORLD, ierr)
    call mpi_comm_rank(mpi_comm_world, rank, ierr)
    call mpi_comm_size(mpi_comm_world, process, ierr)

!    if(.not.valid) then
!        call MPI_Finalize(ierr)
!        stop
!    endif

    ! print *, 'In_fftw_setup after rank common',rank
    !Check that nx != 1.  No quasi 2D simulations are allowed with the MPI interface.
    ! Rather, the arrays MUST be padded to size 2 in the y-direction
    if (ny .eq. 1 .and. process .gt. 1) then
        if (rank .eq. 0) then
            print *, '**************************************************************'
            print *, 'Error: ny = 1 detected.'
            print *, '       Quasi 2D simulations are not allowed with MPI interface'
            print *, '       Attempting recovery by padding to ny = 2!'
            print *, '**************************************************************'
            !'
        endif
        ny = 2
    endif

    call MPI_Barrier(MPI_COMM_WORLD, ierr)
    call fftw_setup_doubleSize_3D_mpi_c(Rn1_doubleSize, Rn2_doubleSize, Rn3_doubleSize, &
                                        Cn1_doubleSize, Cn2_doubleSize, Cn3_doubleSize, &
                                        lstartR_doubleSize, lstart3_doubleSize, &
                                        trans_doubleSize, nx*2, ny*2, nz*2)
    !Prepare the system size for output to the calling routine

    allocate (Rn1_doubleSizeAll(0:process - 1)); Rn1_doubleSizeAll = 0.
    allocate (lstartR_doubleSizeAll(0:process - 1)); lstartR_doubleSizeAll = 0.

    Rn1_doubleSizeAll(rank) = Rn1_doubleSize
    lstartR_doubleSizeAll(rank) = lstartR_doubleSize
    call MPI_Barrier(MPI_Comm_world, ierr)

    do n = 0, process - 1
        call MPI_Bcast(Rn1_doubleSizeAll(n), 1, MPI_integer, n, MPI_Comm_World, ierr)
        call MPI_Bcast(lstartR_doubleSizeAll(n), 1, MPI_integer, n, MPI_Comm_World, ierr)
    enddo
    call MPI_Barrier(MPI_Comm_world, ierr)   !tuy20160531f

end subroutine

module subroutine forward_mpi_doubleSize(fwdx2, fwdx2k)   !tuy02

    ! use mod_fftw_mpi
    !tuy02      use mod_fftw_mpi_doubleSize
    !use mod_interfaces

    implicit none
    real(kind=rdp), intent(in) :: fwdx2(:, :, :)
    complex(kind=cdp), intent(out) :: fwdx2k(:, :, :)

    call fftw_exec_3d_fwd_doubleSize(Cn1_doubleSize, Cn2_doubleSize, Cn3_doubleSize, fwdx2, fwdx2k)

end subroutine

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
module subroutine backward_mpi_doubleSize(fwdx2k, fwdx2)   !tuy02

    ! use mod_fftw_mpi
    !tuy02      use mod_fftw_mpi_doubleSize
    !use mod_interfaces

    implicit none
    complex(kind=cdp), intent(in) :: fwdx2k(:, :, :)
    real(kind=rdp), intent(out) :: fwdx2(:, :, :)

    call fftw_exec_3d_bwd_doubleSize(Rn1_doubleSize, Rn2_doubleSize, Rn3_doubleSize, fwdx2k, fwdx2)

end subroutine

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
module subroutine fftw_setup_2D_mpi(dims, HK, lstart)

    ! use simSize
    ! use mod_fftw_mpi
    ! use print_utilities
    ! use license

    use, intrinsic :: iso_C_binding

    implicit none

    integer, intent(IN), dimension(2) :: dims
    integer, intent(OUT):: HK(2), lstart
    integer i, j, k, n
    logical init_flag
    real(kind=rdp) twopi, fk1
    integer trans_doubleSize   !tuy02
    character(len=78) :: text1

    twopi = 4.d0*atan(1.d0)*2.0
    k1 = dims(1); k2 = dims(2)
    !Check if MPI is currently initialized.  If not, initalize it.
    call MPI_INITIALIZED(init_flag, ierr)
    if (.not. init_flag) call MPI_INIT(ierr)

    ! print *, 'In_fftw_setup',rank
    call MPI_Barrier(MPI_COMM_WORLD, ierr)
    call mpi_comm_rank(mpi_comm_world, rank, ierr)
    call mpi_comm_size(mpi_comm_world, process, ierr)

!    if(.not.valid) then
!        call MPI_Finalize(ierr)
!        stop
!    endif

    ! print *, 'In_fftw_setup after rank common',rank
    !Check that nx != 1.  No quasi 2D simulations are allowed with the MPI interface.
    ! Rather, the arrays MUST be padded to size 2 in the y-direction
    if (ny .eq. 1 .and. process .gt. 1) then
        if (rank .eq. 0) then
            print *, '**************************************************************'
            print *, 'Error: ny = 1 detected.'
            print *, '       Quasi 2D simulations are not allowed with MPI interface'
            print *, '       Attempting recovery by padding to ny = 2!'
            print *, '**************************************************************'
            !'
        endif
        ny = 2
    endif

    call MPI_Barrier(MPI_COMM_WORLD, ierr)
    call fftw_setup_2D_mpi_c(Hn1, Hn2, lstart2, nx, ny)

    !Prepare the system size for output to the calling routine

    HK(1) = Hn1; HK(2) = Hn2
    lstart = lstart2

8003 format('Starting real value (3D/2D) on  ', i2, ' is ', i5)

8005 format('Real simulation size (2D) on    ', i2, ' is ', 2i5)
8006 format('Complex simulation size (2D) on ', i2, ' is ', 2i5)
8007 format('Starting complex value (2D) on  ', i2, ' is ', i5)

    call MPI_BARRIER(MPI_COMM_WORLD, ierr)
    do i = 0, process - 1
        call MPI_BARRIER(MPI_COMM_WORLD, ierr)
        if (rank .eq. i) then
            ! write (text1, 8006) rank, Hn1, Hn2
            ! call printMessage(text1, ' ', 'l')
            ! write (text1, 8007) rank, lstart2
            ! call printMessage(text1, ' ', 'l')
            ! call printMessage("", '-', 'l')

!      write(*,8001) rank,Rn1,Rn2,Rn3
!      write(*,8002) rank,Cn1,Cn2,Cn3
    !  write(*,8003) rank,lstartR
!      write(*,8004) rank,lstart3
    !  write(*,8005) rank,Rn1,Rn2
     write(*,8006) rank,Hn1,Hn2
     write(*,8007) rank,lstart2

        endif
        call MPI_BARRIER(MPI_COMM_WORLD, ierr)
    enddo

    allocate (mqk1_2(Rn3, Hn2, Hn1))
    allocate (mqk2_2(Rn3, Hn2, Hn1))
    !print *, 'Finished allocating'
    !
    !Define the 2D k-vectors
    do k = 1, Hn1
        do j = 1, Hn2
            do i = 1, Rn3
                !kx - vectors
                fk1 = float(lstart2 + k - 1)
                if (fk1 .gt. float(nx)/2) fk1 = fk1 - float(nx)
                mqk1_2(i, j, k) = twopi*fk1/(dx*float(nx))
                !if(i.eq.1.and.j.eq.1.and.rank.eq.0) print *,j, fk1,mqk1_2(i,j,k)

                !ky - vectors
                fk1 = float(j - 1)
                if (fk1 .gt. float(ny)/2) fk1 = fk1 - float(ny)
                mqk2_2(i, j, k) = twopi*fk1/(dy*float(ny))
            enddo
        enddo
    enddo
    !print *, 'found mqki_2'

end subroutine

module subroutine forward2_mpi(fwd, fwdk)

    ! use mod_fftw_mpi
    !use mod_interfaces

    implicit none
    real(kind=rdp), intent(in) :: fwd(:, :, :)
    complex(kind=cdp), intent(out) :: fwdk(:, :, :)

    call fftw_exec_2d_fwd(Hn1, Hn2, size(fwdk, 1), fwd, fwdk)

end subroutine

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
module subroutine backward2_mpi(fwdk, fwd)

    ! use mod_fftw_mpi
    !use mod_interfaces

    implicit none
    complex(kind=cdp), intent(in) :: fwdk(:, :, :)
    real(kind=rdp), intent(out) :: fwd(:, :, :)

    call fftw_exec_2d_bwd(Rn1, Rn2, size(fwd, 1), fwdk, fwd)

end subroutine

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
module subroutine fftw_setup_doubleSize_2D_mpi()

    ! use simSize
    ! use mod_fftw_mpi
    ! use print_utilities
    ! use license

    use, intrinsic :: iso_C_binding

    implicit none

    integer i, j, k, n
    logical init_flag
    real(kind=rdp) twopi, fk1
    integer trans_doubleSize   !tuy02
    character(len=78) :: text1

    twopi = 4.d0*atan(1.d0)*2.0
    !Check if MPI is currently initialized.  If not, initalize it.
    call MPI_INITIALIZED(init_flag, ierr)
    if (.not. init_flag) call MPI_INIT(ierr)

    ! print *, 'In_fftw_setup',rank
    call MPI_Barrier(MPI_COMM_WORLD, ierr)
    call mpi_comm_rank(mpi_comm_world, rank, ierr)
    call mpi_comm_size(mpi_comm_world, process, ierr)

!    if(.not.valid) then
!        call MPI_Finalize(ierr)
!        stop
!    endif

    ! print *, 'In_fftw_setup after rank common',rank
    !Check that nx != 1.  No quasi 2D simulations are allowed with the MPI interface.
    ! Rather, the arrays MUST be padded to size 2 in the y-direction
    if (ny .eq. 1 .and. process .gt. 1) then
        if (rank .eq. 0) then
            print *, '**************************************************************'
            print *, 'Error: ny = 1 detected.'
            print *, '       Quasi 2D simulations are not allowed with MPI interface'
            print *, '       Attempting recovery by padding to ny = 2!'
            print *, '**************************************************************'
            !'
        endif
        ny = 2
    endif

    call MPI_Barrier(MPI_COMM_WORLD, ierr)
    call fftw_setup_doubleSize_2D_mpi_c(Hn1_doubleSize, Hn2_doubleSize, &
                                        lstart2_doubleSize, &
                                        nx*2, ny*2)
    !Prepare the system size for output to the calling routine

end subroutine

end submodule fftw_3D_mpi
