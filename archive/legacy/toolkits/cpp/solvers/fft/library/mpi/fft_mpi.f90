! we need to define two modules, one module only for the subroutines which users can call from
! external program, and the other module contains the data that the library uses, which should be separated
! from the data that user define in the main program. If the user want to associate the library data with
! outside data, he/she needs to do it explicitly with the provided data passing subroutines

module fft_3D_mpi
    use nmathbasic
    implicit none
    include "mpif.h"
    integer ierr
    integer nx, ny, nz, k1, k2
    real(kind=rdp) :: dx, dy, dz
    integer lstartR, lstart2, lstart3 !Starts for distributed last dimension for real, 2D-transform, and 3D-transform arrays, respectively
    integer Rn1, Rn2, Rn3, Cn1, Cn2, Cn3 !Dimension sizes for Real and 3D-transform arrays, respectively
    !Real arrays should be sized f(Rn3,Rn2,Rn1) while 3D-transform arrays should be f(Cn3,Cn2,Cn1)
    integer Hn1, Hn2 !Dimension sizes for 2D-transform arrays.  They should be sized f(Rn3,Hn2,Hn1)
    real(kind=rdp), pointer, dimension(:, :, :) :: mqk1_3, mqk2_3, mqk3_3
    real(kind=rdp), pointer, dimension(:, :, :) :: mqk1_2, mqk2_2
    integer rank, process
    integer lstartR_doubleSize, lstart2_doubleSize, lstart3_doubleSize   !tuy02 All _a -> _doubleSize
    integer Rn1_doubleSize, Rn2_doubleSize, Rn3_doubleSize, Cn1_doubleSize, Cn2_doubleSize, Cn3_doubleSize
    integer Hn1_doubleSize, Hn2_doubleSize
    integer, pointer, dimension(:) :: Rn1All, lstartRAll, Rn1_doubleSizeAll, lstartR_doubleSizeAll !system size parameters Rn1 and lstart of all processes
end module

module public_fft_3D_mpi
    use, intrinsic :: iso_C_binding
    use nmathbasic
    implicit none
    interface

        module subroutine fftw_setup_3D_mpi(dims, ddims, R, C, lstart, trans, Rn1All_out, lstartRAll_out)
            use, intrinsic :: iso_C_binding
            implicit none
            integer, intent(IN), dimension(3) :: dims
            real(kind=rdp), intent(IN), dimension(3) :: ddims
            integer, intent(OUT)::R(3), C(3), lstart(3), trans
            integer, intent(OUT), optional :: Rn1All_out(0:), lstartRAll_out(0:)
        end subroutine

        module subroutine forward_mpi(fwd, fwdk)
            implicit none
            real(kind=rdp), intent(in) :: fwd(:, :, :)
            complex(kind=cdp), intent(out) :: fwdk(:, :, :)
        end subroutine

        module subroutine backward_mpi(fwdk, fwd)
            implicit none
            complex(kind=cdp), intent(in) :: fwdk(:, :, :)
            real(kind=rdp), intent(out) :: fwd(:, :, :)
        end subroutine

        module subroutine fftw_setup_doubleSize_3D_mpi()
        end subroutine

        module subroutine forward_mpi_doubleSize(fwdx2, fwdx2k)   !tuy02
            implicit none
            real(kind=rdp), intent(in) :: fwdx2(:, :, :)
            complex(kind=cdp), intent(out) :: fwdx2k(:, :, :)
        end subroutine

        module subroutine backward_mpi_doubleSize(fwdx2k, fwdx2)   !tuy02
            implicit none
            complex(kind=cdp), intent(in) :: fwdx2k(:, :, :)
            real(kind=rdp), intent(out) :: fwdx2(:, :, :)
        end subroutine

        module subroutine fftw_setup_2D_mpi(dims, HK, lstart)
            use, intrinsic :: iso_C_binding
            implicit none
            integer, intent(IN), dimension(2) :: dims
            integer, intent(OUT):: HK(2), lstart
        end subroutine

        module subroutine forward2_mpi(fwd, fwdk)
            implicit none
            real(kind=rdp), intent(in) :: fwd(:, :, :)
            complex(kind=cdp), intent(out) :: fwdk(:, :, :)
        end subroutine

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        module subroutine backward2_mpi(fwdk, fwd)
            implicit none
            complex(kind=cdp), intent(in) :: fwdk(:, :, :)
            real(kind=rdp), intent(out) :: fwd(:, :, :)
        end subroutine

        module subroutine fftw_setup_doubleSize_2D_mpi()
        end subroutine
    end interface
end module public_fft_3D_mpi
