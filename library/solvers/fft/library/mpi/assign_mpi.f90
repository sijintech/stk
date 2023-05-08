module assign

    implicit none
    contains
subroutine addnoise(array,magnitude,box,seed_in)
    ! use nmathbasic
    ! use mod_fftw_mpi
    ! use simsize
    !use ifport
    use fft_3D_mpi
    implicit none

    real(kind=rdp),dimension(:,:,:),intent(inout) :: array
    real(kind=rdp),dimension(:,:,:),allocatable :: noise
    integer, intent(in),dimension(6),optional :: box
    integer, intent(in),optional :: seed_in
    integer, allocatable :: seed(:)
    integer :: seed_size,i,j,k,seed1
    integer :: xmin,xmax,ymin,ymax,zmin,zmax,x,y,z
    real(kind=rdp),intent(in) :: magnitude
    integer,dimension(8) :: dtVals

    call date_and_time(VALUES=dtVals)
    call random_seed(size=seed_size)
    allocate(seed(seed_size))

    if(present(seed_in)) then
        seed1=seed_in
        seed = seed_in
    else
        seed=dtVals((9-seed_size):8)
    endif

    ! Make the seed related to rank, so that on different cores the random
    ! numbers are different
    seed1 = seed1 + rank
    seed = seed + rank

    ! call srand(seed1)
    call random_seed(put=seed)
    if(present(box)) then
        xmin=box(1)
        xmax=box(2)
        ymin=box(3)
        ymax=box(4)
        zmin=box(5)
        zmax=box(6)
    else
        xmin=1
        xmax=Rn1
        ymin=1
        ymax=Rn2
        zmin=k1
        zmax=k2
    endif

    if(lstartR>=xmin) then
        xmin=1
    else
        xmin=xmin-lstartR
    endif
    if(Rn1+lstartR<=xmax) then
        xmax=Rn1
    else
        xmax=xmax-lstartR
    endif

    x=xmax-xmin+1
    y=ymax-ymin+1
    z=zmax-zmin+1
    allocate(noise(z,y,x))
    ! call random_number(noise)
    ! replace the noise center to 0 rather than 0.5
    do i = 1, z
        do j = 1, y
            do k = 1,x
                call RANDOM_NUMBER(noise(i,j,k))
                ! noise(i,j,k)=rand()
            end do
        end do
    enddo
    noise=noise-0.5
    array(zmin:zmax,ymin:ymax,xmin:xmax) = array(zmin:zmax,ymin:ymax,xmin:xmax) + noise*magnitude
end subroutine addnoise

subroutine setZero(array,box,reverse,maskIn)
    ! use nmathbasic
    use fft_3D_mpi
    ! use simsize
    implicit none

    real(kind=rdp),dimension(:,:,:),intent(inout) :: array
    real(kind=rdp), dimension(:,:,:),allocatable :: tsource,fsource
    integer, intent(in),dimension(6) :: box
    logical, intent(in) :: reverse
    logical, intent(in),dimension(:,:,:),optional :: maskIn
    logical, dimension(:,:,:),allocatable :: mask
    integer :: xmin,xmax,ymin,ymax,zmin,zmax

    allocate(tsource(Rn3,Rn2,Rn1))
    allocate(fsource(Rn3,Rn2,Rn1))
    allocate(mask(Rn3,Rn2,Rn1))
    xmin=box(1)
    xmax=box(2)
    ymin=box(3)
    ymax=box(4)
    zmin=box(5)
    zmax=box(6)
    if(lstartR>=xmin) then
        xmin=1
    else
        xmin=xmin-lstartR
    endif
    if(Rn1+lstartR<=xmax) then
        xmax=Rn1
    else
        xmax=xmax-lstartR
    endif

    mask=.true.
    mask(zmin:zmax,ymin:ymax,xmin:xmax) = .false.

    if(reverse.eqv..true.) then
        ! mask=.true.
        ! mask(zmin:zmax,ymin:ymax,xmin:xmax) = .false.
        if (present(maskIn)) then
            mask = (.not.maskIn).or.mask
        end if
    else
        if (present(maskIn)) then
            mask = maskIn.or.mask
        end if
    endif
    tsource = 0.d0
    fsource = array

    array=merge(tsource,fsource,mask)
end subroutine

end module