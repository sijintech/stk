

SUBROUTINE electric(Kapha, Khom, E_ext_in, el)
    USE globalvars
    use nmathfft
    IMPLICIT NONE

    INTEGER :: ii, jj, kk, i, j, k, l, n
    INTEGER :: iter, nstep1
    REAL*8 :: G_elec(nz, ny, nx), felec(nz, ny, nx), dKdeta(3,3,nz,ny,nx)
    REAL*8, dimension(:,:,:,:,:),intent(in) :: Kapha
    real*8,intent(in) :: E_ext_in(3), Khom(3, 3)
    REAL*8, dimension(:,:,:,:), intent(inout):: el
    REAL*8 :: omega, invomega, nk(3), errorMax

    REAL*8, ALLOCATABLE :: DKE(:, :, :, :)
    REAL*8, ALLOCATABLE :: pot1(:, :, :), pot2(:, :, :), pot3(:, :, :)
    COMPLEX*16, ALLOCATABLE :: pot1k(:, :, :), pot2k(:, :, :), pot3k(:, :, :)
    COMPLEX*16, ALLOCATABLE :: DKEk(:, :, :, :)!, DKEKK(:, :, :, :)
    REAL*8, ALLOCATABLE :: p(:, :, :, :)
    ! REAL*8, ALLOCATABLE :: ell(:, :, :, :)
    COMPLEX*16, ALLOCATABLE :: pk(:, :, :, :)
    COMPLEX*16, ALLOCATABLE :: elk(:, :, :, :)
    REAL*8, ALLOCATABLE :: pot(:, :, :), potold(:, :, :), error(:, :, :)
    COMPLEX*16, ALLOCATABLE :: potk(:, :, :)
    REAL*8, ALLOCATABLE :: DeltaK(:, :, :, :, :), omegaout(:, :, :)

    ALLOCATE (DKE(3, nz, ny, nx))
    ALLOCATE (DKEk(3, nz21, ny, nx))
    ! ALLOCATE (DKEkk(3, nz21, ny, nx))
    ALLOCATE (p(3, nz, ny, nx))
    ! ALLOCATE (ell(3, nz, ny, nx))
    ALLOCATE (pk(3, nz21, ny, nx))
    ALLOCATE (elk(3, nz21, ny, nx))
    ALLOCATE (pot(nz, ny, nx), potold(nz, ny, nx), error(nz, ny, nx))
    ALLOCATE (potk(nz21, ny, nx))
    ALLOCATE (DeltaK(3, 3, nz, ny, nx))
! allocate(pot1(nz,ny,nx))
! allocate(pot2(nz,ny,nx))
! allocate(pot3(nz,ny,nx))

! ALLOCATE(pot1k(nz21,ny,nx))
! ALLOCATE(pot2k(nz21,ny,nx))
! ALLOCATE(pot3k(nz21,ny,nx))

! ALLOCATE(omegaout(nz21,ny,nx))

    ! el(1,:,:,:) = E_ext_in(1)
    ! el(2,:,:,:) = E_ext_in(2)
    ! el(3,:,:,:) = E_ext_in(3)
    ! el=0.d0
    nstep1 = 20
    DO kk = 1, nx
        DO jj = 1, ny
            DO ii = 1, nz
                DO l = 1, 3
                    DO k = 1, 3
                        DeltaK(k, l, ii, jj, kk) = Kapha(k, l, ii, jj, kk) - Khom(k, l)
                    END DO
                END DO
            END DO
        END DO
    END DO

! PRINT *, "DeltaK",DeltaK(:,:,nz,1,1)
! PRINT *, "DeltaK",DeltaK(:,:,nz-1,1,1)

    pk = 0.0
    potk = 0.0
    pot = 0.0
    elk = 0.0
    DO kk = 1, nx
        DO jj = 1, ny
            DO ii = 1, nz
                DO k = 1, 3
                    el(k, ii, jj, kk) = el(k, ii, jj, kk) - E_ext_in(k)
                END DO
            END DO
        END DO
    END DO

    pk = 0.0

!Begin the iterations
    DO 1000 iter = 1, nstep1
        potold = pot

!Calculate DelataK x el
        DKE = 0.0
        DO kk = 1, nx
            DO jj = 1, ny
                DO ii = 1, nz

                    DO j = 1, 3
                        DO i = 1, 3
                            DKE(j, ii, jj, kk) = DKE(j, ii, jj, kk) + DeltaK(i, j, ii, jj, kk)*(el(i, ii, jj, kk) + E_ext_in(i))
                        END DO
                    END DO

                END DO
            END DO
        END DO

        call n_fft_forward("r2c_3d/3", DKE, DKEk)

!Iterative equation
        potk = (0.0, 0.0)
        output = (0.0, 0.0)
        DO kk = 1, nx
            DO jj = 1, ny
                DO ii = 1, nz21
                    omega = 0.0
                    invomega = 0.0
                    ! nk = 0.0

                    ! nk(1) = kx(kk)
                    ! nk(2) = ky(jj)
                    ! nk(3) = kz(ii)

                    DO l = 1, 3
                        DO k = 1, 3
                            ! invomega = invomega + Khom(k,l)*nk(k)*nk(l)
                            invomega = invomega + Khom(k, l)*kvec(k, ii, jj, kk)*kvec(l, ii, jj, kk)
                        END DO
                    END DO

                    IF (ABS(invomega) .GE. 1.0E-8) THEN
                        omega = 1.0/invomega
                    ELSE
                        omega = 0.0
                    END IF

                    DO i = 1, 3
                        ! potk(ii,jj,kk) = potk(ii,jj,kk) - imag*omega*nk(i)*(DKEk(i,ii,jj,kk) + pk(i,ii,jj,kk)/epson0)
                        ! output(ii,jj,kk) = output(ii,jj,kk) - imag*omega*kvec(i,ii,jj,kk)*(DKEk(i,ii,jj,kk) + pk(i,ii,jj,kk)/epson0)
                        potk(ii, jj, kk) = potk(ii, jj, kk) &
                                           - imag*omega*kvec(i, ii, jj, kk) &
                                           *(DKEk(i, ii, jj, kk) + pk(i, ii, jj, kk)/nepsilon0)
                    END DO

                    DO j = 1, 3
                        ! elk(j,ii,jj,kk) = -imag*nk(j)*potk(ii,jj,kk)
                        elk(j, ii, jj, kk) = -imag*kvec(j, ii, jj, kk)*potk(ii, jj, kk)
                    END DO

                END DO
            END DO
        END DO


!  CALL backward(potk,pot)

        call n_fft_backward("r2c_3d", potk, pot)

!  CALL backward(elk(1,:,:,:),el(1,:,:,:))
!  CALL backward(elk(2,:,:,:),el(2,:,:,:))
!  CALL backward(elk(3,:,:,:),el(3,:,:,:))

        call n_fft_backward("r2c_3d/3", elk, el)


!  if(kt.eq.2) then
!  stop
!  endif
!  CALL backward(pot1k(:,:,:),pot1(:,:,:))
!  CALL backward(pot2k(:,:,:),pot2(:,:,:))
!  CALL backward(pot3k(:,:,:),pot3(:,:,:))

        errorMax = 0.0d0
        DO kk = 1, nx
            DO jj = 1, ny
                DO ii = 1, nz
                    error(ii, jj, kk) = dabs(pot(ii, jj, kk) - potold(ii, jj, kk)) !/(dabs(pot(ii,jj,kk))+1.0d-5)
                    if (error(ii, jj, kk) > errorMax) errorMax = error(ii, jj, kk)
                END DO
            END DO
        END DO

        if (errorMax <= 1.0d-3) exit

1000    CONTINUE

        ! print *,"max1",maxval(el),E_ext_in(3)
        DO kk = 1, nx
            DO jj = 1, ny
                DO ii = 1, nz
                    DO j = 1, 3
                        el(j, ii, jj, kk) = el(j, ii, jj, kk) + E_ext_in(j)
                    END DO
                END DO
            END DO
        END DO
        ! print *,"max2",maxval(el),E_ext_in(3)

! PRINT *, "el full after",maxval(el(1,:,:,:)),maxval(el(2,:,:,:)),maxval(el(3,:,:,:)),iter
! PRINT *, "pot full after",pot(:,ny/2+2,nx/2+2)
        DEALLOCATE (DKE)
        DEALLOCATE (DKEk)
        DEALLOCATE (p)
        DEALLOCATE (pk)
        DEALLOCATE (elk)
        DEALLOCATE (pot, potold, error)
        DEALLOCATE (potk)
        DEALLOCATE (DeltaK)

        END SUBROUTINE electric

