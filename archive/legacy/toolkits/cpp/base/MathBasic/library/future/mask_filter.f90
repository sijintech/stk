subroutine maskFilter_real(array,maskIn,reverse)
    use nmathbasic_constants
    ! use mod_fftw_mpi
    ! use simsize
    implicit none
    real(kind=rdp),dimension(:,:,:),intent(inout) :: array
    logical,dimension(:,:,:),intent(in) :: maskIn
    logical,intent(in) :: reverse
    ! print *,"size array",sizeof(array),sizeof(maskIn)
    if (reverse) then
        where (maskIn)
            array=0.d0
        end where

    else
        where (.not.maskIn)
            array=0.d0
        end where
    end if
end subroutine
