module conversion
    use nmathbasic_constants
    implicit none

    interface tensor_to_voigt
        module procedure tensor2voigt_fix
        module procedure tensor2voigt_variable
    endinterface

    interface voigt_to_tensor
        module procedure voigt2tensor_fix
        module procedure voigt2tensor_variable
    endinterface

    interface tensor_to_voigt_flexo
        module procedure tensor2voigt_flexo_fix
        module procedure tensor2voigt_flexo_variable
    end interface


    interface voigt_to_tensor_flexo
        module procedure voigt2tensor_flexo_fix
        module procedure voigt2tensor_flexo_variable
    end interface

    contains
subroutine convertMatrix33To1D(matrixIn, out1D)
    use nmathbasic_constants
    implicit none
    real(kind=rdp), intent(in), dimension(3, 3) :: matrixIn
    real(kind=rdp), intent(out), dimension(6) :: out1D

    out1D(1) = matrixIn(1, 1)
    out1D(2) = matrixIn(2, 2)
    out1D(3) = matrixIn(3, 3)
    out1D(4) = matrixIn(2, 3)
    out1D(5) = matrixIn(1, 3)
    out1D(6) = matrixIn(1, 2)
end subroutine

subroutine convert1DToMatrix33(in1D, matrixOut)
    use nmathbasic_constants
    implicit none
    real(kind=rdp), intent(out), dimension(3, 3) :: matrixOut
    real(kind=rdp), intent(in), dimension(6) :: in1D

    matrixOut(1, 1) = in1D(1)
    matrixOut(2, 2) = in1D(2)
    matrixOut(3, 3) = in1D(3)
    matrixOut(2, 3) = in1D(4)
    matrixOut(1, 3) = in1D(5)
    matrixOut(1, 2) = in1D(6)
    matrixOut(2, 1) = in1D(6)
    matrixOut(3, 1) = in1D(5)
    matrixOut(3, 2) = in1D(4)
end subroutine

subroutine convertVoigt66To1D(tensorIn, out1D)
    use nmathbasic_constants
    implicit none
    real(kind=rdp), dimension(6, 6), intent(in) :: tensorIn
    real(kind=rdp), dimension(21), intent(out) :: out1D
    integer i, j, n

    n = 1
    do i = 1, 6
        do j = i, 6
            out1D(n) = tensorIn(i, j)
            n = n + 1
        end do
    end do
end subroutine

subroutine convert1DToVoigt66(in1D, tensorOut)
    use nmathbasic_constants
    implicit none
    real(kind=rdp), dimension(6, 6), intent(out) :: tensorOut
    real(kind=rdp), dimension(21), intent(in) :: in1D
    integer i, j, n

    n = 1
    do i = 1, 6
        do j = i, 6
            tensorOut(i, j) = in1D(n)
            tensorOut(j, i) = tensorOut(i, j)
            n = n + 1
        end do
    end do

end subroutine

subroutine create_voigt_rank4_cubic_homo(voigtOut,x11,x12,x44)
    implicit none
    real(kind=rdp),dimension(6,6),intent(out) :: voigtOut
    real(kind=rdp),intent(in) :: x11,x12,x44

    voigtOut = 0.d0
    voigtOut(1,1) = x11 ; voigtOut(1,2) = x12 ; voigtOut(1,3) = x12
    voigtOut(2,1) = x12 ; voigtOut(2,2) = x11 ; voigtOut(2,3) = x12
    voigtOut(3,1) = x12 ; voigtOut(3,2) = x12 ; voigtOut(3,3) = x11
    voigtOut(4,4) = x44
    voigtOut(5,5) = x44
    voigtOut(6,6) = x44
end subroutine

subroutine create_tensor_rank4_cubic_homo(tensorOut,x11,x12,x44,multiplier)
    implicit none
    real(kind=rdp),dimension(3,3,3,3),intent(out) :: tensorOut
    real(kind=rdp),intent(in)::x11,x12,x44
    real(kind=rdp),dimension(6,6) :: voigt
    logical,intent(in) :: multiplier

    call create_voigt_rank4_cubic_homo(voigt,x11,x12,x44)
    call voigt2tensor_fix(voigt,tensorOut,multiplier)
end subroutine

subroutine tensor2voigt_flexo_fix(tensor,voigt,inverse)
    ! use fft_3D_mpi
    implicit none
    real(kind=rdp),dimension(:,:),intent(out)::voigt
    real(kind=rdp),dimension(3,3,3,3),intent(in)::tensor
    logical,intent(in)::inverse

    integer(kind=idp) :: i,j,k,l,m,n
    real(kind=rdp) :: mult1,mult2

    ! for F_ijkl and f_ijkl
    ! ij corresponds to strain/stress indices ij
    ! k corresponds to Polarization/electric field indices k
    ! l corresponds to spatial derivative l

    ! For clarity, the "Voigt" matrix notation and tensor notation does not contain multiplyers
    ! Care need to be paid when using the "Voigt" matrix notation to multiply
    ! other vectors, if multiply 2 or 0.5 is needed or not !

    ! The flag inverse is for converse (inverse) flexo coefficients
    ! which is exactly the same is direct coefficients if the indices ording are
    ! the same
    ! i.e. F^dir_ijkl === F^inv_ijkl, where ij is for s/e and k for P/E, l for x

    if(.not.inverse) then
        do i = 1,3
            do j = 1,3
                do k = 1,3
                    do l = 1,3
                        m = k
                        if(i==1.and.j==1.and.l==1) then; n = 1; endif
                        if(i==1.and.j==1.and.l==2) then; n = 2; endif
                        if(i==1.and.j==1.and.l==3) then; n = 3; endif
                        if(i==2.and.j==2.and.l==1) then; n = 4; endif
                        if(i==2.and.j==2.and.l==2) then; n = 5; endif
                        if(i==2.and.j==2.and.l==3) then; n = 6; endif
                        if(i==3.and.j==3.and.l==1) then; n = 7; endif
                        if(i==3.and.j==3.and.l==2) then; n = 8; endif
                        if(i==3.and.j==3.and.l==3) then; n = 9; endif
                        if((i==1.and.j==2.and.l==1).or.(i==2.and.j==1.and.l==1)) then; n = 10; endif
                        if((i==1.and.j==2.and.l==2).or.(i==2.and.j==1.and.l==2)) then; n = 11; endif
                        if((i==1.and.j==2.and.l==3).or.(i==2.and.j==1.and.l==3)) then; n = 12; endif
                        if((i==1.and.j==3.and.l==1).or.(i==3.and.j==1.and.l==1)) then; n = 13; endif
                        if((i==1.and.j==3.and.l==2).or.(i==3.and.j==1.and.l==2)) then; n = 14; endif
                        if((i==1.and.j==3.and.l==3).or.(i==3.and.j==1.and.l==3)) then; n = 15; endif
                        if((i==3.and.j==2.and.l==1).or.(i==2.and.j==3.and.l==1)) then; n = 16; endif
                        if((i==3.and.j==2.and.l==2).or.(i==2.and.j==3.and.l==2)) then; n = 17; endif
                        if((i==3.and.j==2.and.l==3).or.(i==2.and.j==3.and.l==3)) then; n = 18; endif
                        voigt(m,n) = tensor(i,j,k,l)
                    enddo
                enddo
            enddo
        enddo
    else
        do i = 1,3
            do j = 1,3
                do k = 1,3
                    do l = 1,3
                        IF (i == j) then; m = i; endif
                        IF ((i == 2 .AND. j == 3) .OR. ( i == 3 .AND. j == 2)) then; m = 4; endif
                        IF ((i == 1 .AND. j == 3) .OR. ( i == 3 .AND. j == 1)) then; m = 5; endif
                        IF ((i == 1 .AND. j == 2) .OR. ( i == 2 .AND. j == 1)) then; m = 6; endif
                        if (k==1.and.l==1) then; n = 1; endif
                        if (k==1.and.l==2) then; n = 2; endif
                        if (k==1.and.l==3) then; n = 3; endif
                        if (k==2.and.l==1) then; n = 4; endif
                        if (k==2.and.l==2) then; n = 5; endif
                        if (k==2.and.l==3) then; n = 6; endif
                        if (k==3.and.l==1) then; n = 7; endif
                        if (k==3.and.l==2) then; n = 8; endif
                        if (k==3.and.l==3) then; n = 9; endif
                        voigt(m,n) = tensor(i,j,k,l)
                    enddo
                enddo
            enddo
        enddo
    endif

end subroutine

subroutine tensor2voigt_flexo_variable(tensor,voigt,inverse)
    !use mod_interfaces
    ! use fft_3D_mpi
    implicit none
    real(kind=rdp),dimension(:,:,:,:,:),intent(out)::voigt
    real(kind=rdp),dimension(:,:,:,:,:,:,:),intent(in)::tensor
    logical,intent(in)::inverse

    integer(kind=idp) :: i,j,k,l,m,n
    real(kind=rdp) :: mult1,mult2

    ! for F_ijkl and f_ijkl
    ! ij corresponds to strain/stress indices ij
    ! k corresponds to Polarization/electric field indices k
    ! l corresponds to spatial derivative l

    ! For clarity, the "Voigt" matrix notation and tensor notation does not contain multiplyers
    ! Care need to be paid when using the "Voigt" matrix notation to multiply
    ! other vectors, if multiply 2 or 0.5 is needed or not !

    ! The flag inverse is for converse (inverse) flexo coefficients
    ! which is exactly the same is direct coefficients if the indices ording are
    ! the same
    ! i.e. F^dir_ijkl === F^inv_ijkl, where ij is for s/e and k for P/E, l for x

    ! if (size(tensor,1).ne.3 .or. size(tensor,2).ne.3 .or. size(tensor,3).ne.3 .or. size(tensor,4).ne.3) then
    !     if (rank==0) then
    !         print *,"The size of the tensor to convert to voigt notation is not correct"
    !         call MPI_Finalize(ierr)
    !         stop
    !     endif
    ! endif

    if(.not.inverse) then
        do i = 1,3
            do j = 1,3
                do k = 1,3
                    do l = 1,3
                        m = k
                        if(i==1.and.j==1.and.l==1) then; n = 1; endif
                        if(i==1.and.j==1.and.l==2) then; n = 2; endif
                        if(i==1.and.j==1.and.l==3) then; n = 3; endif
                        if(i==2.and.j==2.and.l==1) then; n = 4; endif
                        if(i==2.and.j==2.and.l==2) then; n = 5; endif
                        if(i==2.and.j==2.and.l==3) then; n = 6; endif
                        if(i==3.and.j==3.and.l==1) then; n = 7; endif
                        if(i==3.and.j==3.and.l==2) then; n = 8; endif
                        if(i==3.and.j==3.and.l==3) then; n = 9; endif
                        if((i==1.and.j==2.and.l==1).or.(i==2.and.j==1.and.l==1)) then; n = 10; endif
                        if((i==1.and.j==2.and.l==2).or.(i==2.and.j==1.and.l==2)) then; n = 11; endif
                        if((i==1.and.j==2.and.l==3).or.(i==2.and.j==1.and.l==3)) then; n = 12; endif
                        if((i==1.and.j==3.and.l==1).or.(i==3.and.j==1.and.l==1)) then; n = 13; endif
                        if((i==1.and.j==3.and.l==2).or.(i==3.and.j==1.and.l==2)) then; n = 14; endif
                        if((i==1.and.j==3.and.l==3).or.(i==3.and.j==1.and.l==3)) then; n = 15; endif
                        if((i==3.and.j==2.and.l==1).or.(i==2.and.j==3.and.l==1)) then; n = 16; endif
                        if((i==3.and.j==2.and.l==2).or.(i==2.and.j==3.and.l==2)) then; n = 17; endif
                        if((i==3.and.j==2.and.l==3).or.(i==2.and.j==3.and.l==3)) then; n = 18; endif
                        voigt(m,n,:,:,:) = tensor(i,j,k,l,:,:,:)
                    enddo
                enddo
            enddo
        enddo
    else
        do i = 1,3
            do j = 1,3
                do k = 1,3
                    do l = 1,3
                        IF (i == j) then; m = i; endif
                        IF ((i == 2 .AND. j == 3) .OR. ( i == 3 .AND. j == 2)) then; m = 4; endif
                        IF ((i == 1 .AND. j == 3) .OR. ( i == 3 .AND. j == 1)) then; m = 5; endif
                        IF ((i == 1 .AND. j == 2) .OR. ( i == 2 .AND. j == 1)) then; m = 6; endif
                        if (k==1.and.l==1) then; n = 1; endif
                        if (k==1.and.l==2) then; n = 2; endif
                        if (k==1.and.l==3) then; n = 3; endif
                        if (k==2.and.l==1) then; n = 4; endif
                        if (k==2.and.l==2) then; n = 5; endif
                        if (k==2.and.l==3) then; n = 6; endif
                        if (k==3.and.l==1) then; n = 7; endif
                        if (k==3.and.l==2) then; n = 8; endif
                        if (k==3.and.l==3) then; n = 9; endif
                        voigt(m,n,:,:,:) = tensor(i,j,k,l,:,:,:)
                    enddo
                enddo
            enddo
        enddo
    endif
end subroutine


subroutine tensor2voigt_fix(tensor,voigt,multiply)
    !use mod_interfaces
    ! use fft_3D_mpi
    implicit none
    real(kind=rdp),dimension(6,6),intent(out)::voigt
    real(kind=rdp),dimension(3,3,3,3),intent(in)::tensor
    logical,intent(in)::multiply

    integer(kind=idp) :: i,j,k,l,m,n
    real(kind=rdp) :: mult1,mult2


    do i = 1,3
        do j = 1,3
            do k = 1,3
                do l = 1,3
                    IF (i == j) then; m = i; mult1=1.; endif
                    IF ((i == 2 .AND. j == 3) .OR. ( i == 3 .AND. j == 2)) then; m = 4; mult1=2.; endif
                    IF ((i == 1 .AND. j == 3) .OR. ( i == 3 .AND. j == 1)) then; m = 5; mult1=2.; endif
                    IF ((i == 1 .AND. j == 2) .OR. ( i == 2 .AND. j == 1)) then; m = 6; mult1=2.; endif
                    IF (k == l) then; n = k; mult2=1.; endif
                    IF ((k == 2 .AND. l == 3) .OR. ( k == 3 .AND. l == 2)) then; n = 4; mult2=2.; endif
                    IF ((k == 1 .AND. l == 3) .OR. ( k == 3 .AND. l == 1)) then; n = 5; mult2=2.; endif
                    IF ((k == 1 .AND. l == 2) .OR. ( k == 2 .AND. l == 1)) then; n = 6; mult2=2.; endif
                    if (multiply) then
                        voigt(m,n) = tensor(i,j,k,l)*mult1*mult2
                    else
                        voigt(m,n) = tensor(i,j,k,l)
                    endif
                enddo
            enddo
        enddo
    enddo
end subroutine

subroutine tensor2voigt_variable(tensor,voigt,multiply)
    !use mod_interfaces
    ! use fft_3D_mpi

    implicit none
    real(kind=rdp),dimension(:,:,:,:,:),intent(out)::voigt
    real(kind=rdp),dimension(:,:,:,:,:,:,:),intent(in)::tensor
    logical,intent(in)::multiply

    integer(kind=idp) :: i,j,k,l,m,n
    real(kind=rdp):: mult1,mult2

    ! if (size(tensor,1).ne.3 .or. size(tensor,2).ne.3 .or. size(tensor,3).ne.3 .or. size(tensor,4).ne.3) then
    !     if (rank==0) then
    !         print *,"The size of the tensor to convert to voigt notation is not correct"
    !         call MPI_Finalize(ierr)
    !         stop
    !     endif
    ! endif
    do i = 1,3
        do j = 1,3
            do k = 1,3
                do l = 1,3
                    IF (i == j) then; m = i; mult1=1.; endif
                    IF ((i == 2 .AND. j == 3) .OR. ( i == 3 .AND. j == 2)) then; m = 4; mult1=2.; endif
                    IF ((i == 1 .AND. j == 3) .OR. ( i == 3 .AND. j == 1)) then; m = 5; mult1=2.; endif
                    IF ((i == 1 .AND. j == 2) .OR. ( i == 2 .AND. j == 1)) then; m = 6; mult1=2.; endif
                    IF (k == l) then; n = k; mult2=1.; endif
                    IF ((k == 2 .AND. l == 3) .OR. ( k == 3 .AND. l == 2)) then; n = 4; mult2=2.; endif
                    IF ((k == 1 .AND. l == 3) .OR. ( k == 3 .AND. l == 1)) then; n = 5; mult2=2.; endif
                    IF ((k == 1 .AND. l == 2) .OR. ( k == 2 .AND. l == 1)) then; n = 6; mult2=2.; endif
                    if (multiply) then
                        voigt(m,n,:,:,:) = tensor(i,j,k,l,:,:,:)*mult1*mult2
                    else
                        voigt(m,n,:,:,:) = tensor(i,j,k,l,:,:,:)
                    endif
                enddo
            enddo
        enddo
    enddo
end subroutine

subroutine voigt2tensor_flexo_fix(voigt,tensor,inverse)
    !use mod_interfaces
    ! use fft_3D_mpi

    implicit none
    real(kind=rdp),dimension(:,:),intent(in)::voigt
    real(kind=rdp),dimension(3,3,3,3),intent(out)::tensor
    logical,intent(in)::inverse

    integer(kind=idp) :: i,j,k,l,m,n
    real(kind=rdp)::mult1,mult2

    ! for F_ijkl and f_ijkl
    ! ij corresponds to strain/stress indices ij
    ! k corresponds to Polarization/electric field indices k
    ! l corresponds to spatial derivative l

    ! For clarity, the "Voigt" matrix notation and tensor notation does not contain multiplyers
    ! Care need to be paid when using the "Voigt" matrix notation to multiply
    ! other vectors, if multiply 2 or 0.5 is needed or not !

    ! The flag inverse is for converse (inverse) flexo coefficients
    ! which is exactly the same is direct coefficients if the indices ording are
    ! the same
    ! i.e. F^dir_ijkl === F^inv_ijkl, where ij is for s/e and k for P/E, l for x

    if(.not.inverse) then
        do i = 1,3
            do j = 1,3
                do k = 1,3
                    do l = 1,3
                        m = k
                        if(i==1.and.j==1.and.l==1) then; n = 1; endif
                        if(i==1.and.j==1.and.l==2) then; n = 2; endif
                        if(i==1.and.j==1.and.l==3) then; n = 3; endif
                        if(i==2.and.j==2.and.l==1) then; n = 4; endif
                        if(i==2.and.j==2.and.l==2) then; n = 5; endif
                        if(i==2.and.j==2.and.l==3) then; n = 6; endif
                        if(i==3.and.j==3.and.l==1) then; n = 7; endif
                        if(i==3.and.j==3.and.l==2) then; n = 8; endif
                        if(i==3.and.j==3.and.l==3) then; n = 9; endif
                        if((i==1.and.j==2.and.l==1).or.(i==2.and.j==1.and.l==1)) then; n = 10; endif
                        if((i==1.and.j==2.and.l==2).or.(i==2.and.j==1.and.l==2)) then; n = 11; endif
                        if((i==1.and.j==2.and.l==3).or.(i==2.and.j==1.and.l==3)) then; n = 12; endif
                        if((i==1.and.j==3.and.l==1).or.(i==3.and.j==1.and.l==1)) then; n = 13; endif
                        if((i==1.and.j==3.and.l==2).or.(i==3.and.j==1.and.l==2)) then; n = 14; endif
                        if((i==1.and.j==3.and.l==3).or.(i==3.and.j==1.and.l==3)) then; n = 15; endif
                        if((i==3.and.j==2.and.l==1).or.(i==2.and.j==3.and.l==1)) then; n = 16; endif
                        if((i==3.and.j==2.and.l==2).or.(i==2.and.j==3.and.l==2)) then; n = 17; endif
                        if((i==3.and.j==2.and.l==3).or.(i==2.and.j==3.and.l==3)) then; n = 18; endif
                        tensor(i,j,k,l) = voigt(m,n)
                    enddo
                enddo
            enddo
        enddo
    else
        do i = 1,3
            do j = 1,3
                do k = 1,3
                    do l = 1,3
                        IF (i == j) then; m = i; endif
                        IF ((i == 2 .AND. j == 3) .OR. ( i == 3 .AND. j == 2)) then; m = 4; endif
                        IF ((i == 1 .AND. j == 3) .OR. ( i == 3 .AND. j == 1)) then; m = 5; endif
                        IF ((i == 1 .AND. j == 2) .OR. ( i == 2 .AND. j == 1)) then; m = 6; endif
                        if (k==1.and.l==1) then; n = 1; endif
                        if (k==1.and.l==2) then; n = 2; endif
                        if (k==1.and.l==3) then; n = 3; endif
                        if (k==2.and.l==1) then; n = 4; endif
                        if (k==2.and.l==2) then; n = 5; endif
                        if (k==2.and.l==3) then; n = 6; endif
                        if (k==3.and.l==1) then; n = 7; endif
                        if (k==3.and.l==2) then; n = 8; endif
                        if (k==3.and.l==3) then; n = 9; endif
                        tensor(i,j,k,l) = voigt(m,n)
                    enddo
                enddo
            enddo
        enddo
    endif

end subroutine

subroutine voigt2tensor_flexo_variable(tensor,voigt,inverse)
    !use mod_interfaces
    ! use fft_3D_mpi
    implicit none
    real(kind=rdp),dimension(:,:,:,:,:),intent(in)::voigt
    real(kind=rdp),dimension(:,:,:,:,:,:,:),intent(out)::tensor
    logical,intent(in)::inverse

    integer(kind=idp) :: i,j,k,l,m,n
    real(kind=rdp) :: mult1,mult2

    ! for F_ijkl and f_ijkl
    ! ij corresponds to strain/stress indices ij
    ! k corresponds to Polarization/electric field indices k
    ! l corresponds to spatial derivative l

    ! For clarity, the "Voigt" matrix notation and tensor notation does not contain multiplyers
    ! Care need to be paid when using the "Voigt" matrix notation to multiply
    ! other vectors, if multiply 2 or 0.5 is needed or not !

    ! The flag inverse is for converse (inverse) flexo coefficients
    ! which is exactly the same is direct coefficients if the indices ording are
    ! the same
    ! i.e. F^dir_ijkl === F^inv_ijkl, where ij is for s/e and k for P/E, l for x

    ! if (.not.(size(voigt,1).ne.6.and.size(voigt,2).ne.9).and..not.(size(voigt,1).ne.3.and.size(voigt,2).ne.18)) then
    !     if (rank==0) then
    !         print *,"The size of the voigt notation to convert to tensor notation is not correct"
    !         call MPI_Finalize(ierr)
    !         stop
    !     endif
    ! endif

    if(.not.inverse) then
        do i = 1,3
            do j = 1,3
                do k = 1,3
                    do l = 1,3
                        m = k
                        if(i==1.and.j==1.and.l==1) then; n = 1; endif
                        if(i==1.and.j==1.and.l==2) then; n = 2; endif
                        if(i==1.and.j==1.and.l==3) then; n = 3; endif
                        if(i==2.and.j==2.and.l==1) then; n = 4; endif
                        if(i==2.and.j==2.and.l==2) then; n = 5; endif
                        if(i==2.and.j==2.and.l==3) then; n = 6; endif
                        if(i==3.and.j==3.and.l==1) then; n = 7; endif
                        if(i==3.and.j==3.and.l==2) then; n = 8; endif
                        if(i==3.and.j==3.and.l==3) then; n = 9; endif
                        if((i==1.and.j==2.and.l==1).or.(i==2.and.j==1.and.l==1)) then; n = 10; endif
                        if((i==1.and.j==2.and.l==2).or.(i==2.and.j==1.and.l==2)) then; n = 11; endif
                        if((i==1.and.j==2.and.l==3).or.(i==2.and.j==1.and.l==3)) then; n = 12; endif
                        if((i==1.and.j==3.and.l==1).or.(i==3.and.j==1.and.l==1)) then; n = 13; endif
                        if((i==1.and.j==3.and.l==2).or.(i==3.and.j==1.and.l==2)) then; n = 14; endif
                        if((i==1.and.j==3.and.l==3).or.(i==3.and.j==1.and.l==3)) then; n = 15; endif
                        if((i==3.and.j==2.and.l==1).or.(i==2.and.j==3.and.l==1)) then; n = 16; endif
                        if((i==3.and.j==2.and.l==2).or.(i==2.and.j==3.and.l==2)) then; n = 17; endif
                        if((i==3.and.j==2.and.l==3).or.(i==2.and.j==3.and.l==3)) then; n = 18; endif
                        tensor(i,j,k,l,:,:,:) = voigt(m,n,:,:,:)
                    enddo
                enddo
            enddo
        enddo
    else
        do i = 1,3
            do j = 1,3
                do k = 1,3
                    do l = 1,3
                        IF (i == j) then; m = i; endif
                        IF ((i == 2 .AND. j == 3) .OR. ( i == 3 .AND. j == 2)) then; m = 4; endif
                        IF ((i == 1 .AND. j == 3) .OR. ( i == 3 .AND. j == 1)) then; m = 5; endif
                        IF ((i == 1 .AND. j == 2) .OR. ( i == 2 .AND. j == 1)) then; m = 6; endif
                        if (k==1.and.l==1) then; n = 1; endif
                        if (k==1.and.l==2) then; n = 2; endif
                        if (k==1.and.l==3) then; n = 3; endif
                        if (k==2.and.l==1) then; n = 4; endif
                        if (k==2.and.l==2) then; n = 5; endif
                        if (k==2.and.l==3) then; n = 6; endif
                        if (k==3.and.l==1) then; n = 7; endif
                        if (k==3.and.l==2) then; n = 8; endif
                        if (k==3.and.l==3) then; n = 9; endif
                        tensor(i,j,k,l,:,:,:) = voigt(m,n,:,:,:)
                    enddo
                enddo
            enddo
        enddo
    endif
end subroutine


subroutine voigt2tensor_fix(voigt,tensor,multiply)
    !use mod_interfaces
    ! use fft_3D_mpi

    implicit none
    real(kind=rdp),dimension(6,6),intent(in)::voigt
    real(kind=rdp),dimension(3,3,3,3),intent(out)::tensor
    logical,intent(in)::multiply

    integer(kind=idp) :: i,j,k,l,m,n
    real(kind=rdp)::mult1,mult2


    do i = 1,3
        do j = 1,3
            do k = 1,3
                do l = 1,3
                    IF (i == j) then; m = i; mult1=1.; endif
                    IF ((i == 2 .AND. j == 3) .OR. ( i == 3 .AND. j == 2)) then; m = 4; mult1=0.5; endif
                    IF ((i == 1 .AND. j == 3) .OR. ( i == 3 .AND. j == 1)) then; m = 5; mult1=0.5; endif
                    IF ((i == 1 .AND. j == 2) .OR. ( i == 2 .AND. j == 1)) then; m = 6; mult1=0.5; endif
                    IF (k == l) then; n = k; mult2=1.; endif
                    IF ((k == 2 .AND. l == 3) .OR. ( k == 3 .AND. l == 2)) then; n = 4; mult2=0.5; endif
                    IF ((k == 1 .AND. l == 3) .OR. ( k == 3 .AND. l == 1)) then; n = 5; mult2=0.5; endif
                    IF ((k == 1 .AND. l == 2) .OR. ( k == 2 .AND. l == 1)) then; n = 6; mult2=0.5; endif
                    if (multiply) then
                        tensor(i,j,k,l) = voigt(m,n)*mult1*mult2
                    else
                        tensor(i,j,k,l) = voigt(m,n)
                    endif
                enddo
            enddo
        enddo
    enddo
end subroutine


subroutine voigt2tensor_variable(voigt,tensor,multiply)
    !use mod_interfaces
    ! use fft_3D_mpi

    implicit none
    real(kind=rdp),dimension(:,:,:,:,:),intent(in)::voigt
    real(kind=rdp),dimension(:,:,:,:,:,:,:),intent(out)::tensor
    logical,intent(in)::multiply
    integer(kind=idp) :: i,j,k,l,m,n
    real(kind=rdp) :: mult1,mult2

    ! if (size(voigt,1).ne.6 .or. size(voigt,2).ne.6) then
    !     if (rank==0) then
    !         print *,"The size of the voigt notation to convert to tensor notation is not correct"
    !         call MPI_Finalize(ierr)
    !         stop
    !     endif
    ! endif
    do i = 1,3
        do j = 1,3
            do k = 1,3
                do l = 1,3
                    IF (i == j) then; m = i; mult1=1.; endif
                    IF ((i == 2 .AND. j == 3) .OR. ( i == 3 .AND. j == 2)) then; m = 4; mult1=0.5; endif
                    IF ((i == 1 .AND. j == 3) .OR. ( i == 3 .AND. j == 1)) then; m = 5; mult1=0.5; endif
                    IF ((i == 1 .AND. j == 2) .OR. ( i == 2 .AND. j == 1)) then; m = 6; mult1=0.5; endif
                    IF (k == l) then; n = k; mult2=1.; endif
                    IF ((k == 2 .AND. l == 3) .OR. ( k == 3 .AND. l == 2)) then; n = 4; mult2=0.5; endif
                    IF ((k == 1 .AND. l == 3) .OR. ( k == 3 .AND. l == 1)) then; n = 5; mult2=0.5; endif
                    IF ((k == 1 .AND. l == 2) .OR. ( k == 2 .AND. l == 1)) then; n = 6; mult2=0.5; endif
                    if (multiply) then
                        tensor(i,j,k,l,:,:,:) = voigt(m,n,:,:,:)*mult1*mult2
                    else
                        tensor(i,j,k,l,:,:,:) = voigt(m,n,:,:,:)
                    endif
                enddo
            enddo
        enddo
    enddo
end subroutine

end module