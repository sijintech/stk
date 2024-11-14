module array_operation_mpi
    implicit none
    interface

        module subroutine maxArray4(maxima, array, flagAbs)
            use nmathbasic_constants
            implicit none
            real(kind=rdp), intent(out) :: maxima
            real(kind=rdp), dimension(:, :, :, :), intent(in) :: array
            logical, intent(in) :: flagAbs
        end subroutine maxArray4

        module subroutine maxArray3(maxima, array, flagAbs)
            use nmathbasic_constants
            implicit none
            real(kind=rdp), intent(out) :: maxima
            real(kind=rdp), dimension(:, :, :), intent(in) :: array
            logical, intent(in) :: flagAbs
        end subroutine maxArray3

        module subroutine sumBox(total, array, box)
            use nmathbasic_constants
            implicit none
            real(kind=rdp), dimension(:, :, :), intent(in) :: array
            real(kind=rdp), intent(out) :: total
            integer, dimension(6), optional, intent(in) :: box
        end subroutine sumBox

        module subroutine avgBox(avg, array, flagAbs, box)
            use nmathbasic_constants
            implicit none
            real(kind=rdp), intent(out) :: avg
            real(kind=rdp), dimension(:, :, :), intent(in) :: array
            logical, intent(in) :: flagAbs
            integer, dimension(6), optional, intent(in) :: box
        end subroutine avgBox

        module subroutine minBox(minima, array, flagAbs, box)
            use nmathbasic_constants
            implicit none
            real(kind=rdp), intent(out) :: minima
            real(kind=rdp), dimension(:, :, :), intent(in) :: array
            integer, dimension(6), optional, intent(in) :: box
            logical, intent(in) :: flagAbs
        end subroutine minBox

        module subroutine maxBox(maxima, array, flagAbs, box)
            use nmathbasic_constants
            implicit none
            real(kind=rdp), intent(out) :: maxima
            real(kind=rdp), dimension(:, :, :), intent(in) :: array
            integer, dimension(6), optional, intent(in) :: box
            logical, intent(in) :: flagAbs
        end subroutine maxBox
    end interface
end module array_operation_mpi
