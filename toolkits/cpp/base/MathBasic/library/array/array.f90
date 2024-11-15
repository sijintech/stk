module nmathbasic_array
    use iso_fortran_env
    use iso_c_binding
    implicit none
    interface
        subroutine n_data_1D_double_min_index_c(out, n, in) bind(c, name="n_data_1D_double_min_index_f")
            use, intrinsic::iso_c_binding, only: c_char, c_int, c_ptr
            type(c_ptr) :: in
            integer(c_int), intent(in) :: n
            integer(c_int), intent(out) :: out
        end subroutine

        subroutine n_data_1D_double_max_index_c(out, n, in) bind(c, name="n_data_1D_double_max_index_f")
            use, intrinsic::iso_c_binding, only: c_char, c_int, c_ptr
            type(c_ptr) :: in
            integer(c_int), intent(in) :: n
            integer(c_int), intent(out) :: out
        end subroutine

        subroutine n_data_3D_int_exist_range_c(out, x, y, z, array, value) bind(c,name="n_data_3D_int_exist_range_f")
            use, intrinsic::iso_c_binding, only: c_int, c_ptr
            type(c_ptr) :: array, out
            integer(c_int), intent(in) :: x,y,z, value
        end subroutine
    end interface

    contains
    subroutine n_data_1D_double_min_index(out, in)
        use, intrinsic::iso_c_binding
        implicit none
        integer :: n
        real(kind=8) :: in(:)
        integer, intent(out) :: out
        real(kind=8), allocatable, target :: temp(:)
        n = size(in)
        allocate (temp(n))
        temp = in
        call n_data_1D_double_min_index_c(out, n, c_loc(temp))
    end subroutine

    subroutine n_data_1D_double_max_index(out, in)
        use, intrinsic::iso_c_binding
        implicit none
        integer :: n
        real(kind=8) :: in(:)
        integer, intent(out) :: out
        real(kind=8), allocatable, target :: temp(:)
        n = size(in)
        allocate (temp(n))
        temp = in
        call n_data_1D_double_max_index_c(out, n, c_loc(temp))
    end subroutine

    subroutine n_data_3D_int_exist_range(out,in,value)
        use, intrinsic:: iso_c_binding
        implicit none
        integer :: x,y,z
        integer,intent(in) :: value
        integer(kind=int32),dimension(6),intent(out),target :: out
        integer(kind=int32),dimension(:,:,:),intent(in),target :: in
        x = size(in,1)
        y = size(in,2)
        z = size(in,3)
        call n_data_3D_int_exist_range_c(c_loc(out),x,y,z,c_loc(in),value)
    end subroutine
end module