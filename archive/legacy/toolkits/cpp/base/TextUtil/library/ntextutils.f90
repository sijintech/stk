module ntextutils
    use iso_c_binding
    implicit none
    interface
        integer(c_int) function n_string_equal_c(a, b) bind(c, name="n_string_equal")
            use, intrinsic :: iso_c_binding, only: c_char, c_int
            character(kind=c_char), intent(in), dimension(*) :: a, b
        end function n_string_equal_c
    end interface

contains

    integer function n_string_equal(a, b) result(out)
        use, intrinsic :: iso_c_binding, only: c_char, c_int
        character(len=*), intent(in) :: a, b
        character(len=100) :: a_c, b_c
        a_c = a//char(0)
        b_c = b//char(0)
        out = n_string_equal_c(a_c,b_c)
    end function
end module
