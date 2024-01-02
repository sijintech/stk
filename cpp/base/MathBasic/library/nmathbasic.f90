module nmathbasic
    use iso_c_binding
    use nmathbasic_constants
    use nmathbasic_array
    implicit none

    interface
    subroutine n_tensor_rank2_from_voigt_c(x, y, z, voigt, tensor, isstrain) bind(c, name="n_tensor_rank2_from_voigt_f")
        use, intrinsic:: iso_c_binding, only: c_char, c_int, c_ptr
        type(c_ptr) :: tensor, voigt
        integer(c_int), intent(in) :: x, y, z, isstrain
    end subroutine

    subroutine n_tensor_rank2_to_voigt_c(x, y, z, tensor, voigt, isstrain) bind(c, name="n_tensor_rank2_to_voigt_f")
        use, intrinsic::iso_c_binding, only: c_char, c_int, c_ptr
        type(c_ptr) :: tensor, voigt
        integer(c_int), intent(in) :: x, y, z, isstrain
    end subroutine

    end interface
contains
    subroutine n_tensor_rank2_from_voigt(voigt, tensor, isstrain)
        use, intrinsic :: iso_c_binding
        implicit none
        integer::x, y, z
        real(kind=8), target :: tensor(:, :, :, :, :), voigt(:, :, :, :)
        integer, intent(in) :: isstrain
        x = size(tensor, 5)
        y = size(tensor, 4)
        z = size(tensor, 3)
        ! print *,"size of the voigt and tensor",size(voigt,1),size(tensor,1),size(tensor,2)
        call n_tensor_rank2_from_voigt_c(x, y, z, c_loc(voigt), c_loc(tensor), isstrain)
    end subroutine

    subroutine n_tensor_rank2_to_voigt(tensor, voigt, isstrain)
        use, intrinsic :: iso_c_binding
        implicit none
        integer::x, y, z
        real(kind=8), target :: tensor(:, :, :, :, :), voigt(:, :, :, :)
        integer, intent(in) :: isstrain
        x = size(voigt, 4)
        y = size(voigt, 3)
        z = size(voigt, 2)
        call n_tensor_rank2_to_voigt_c(x, y, z, c_loc(tensor), c_loc(voigt), isstrain)
    end subroutine
end module