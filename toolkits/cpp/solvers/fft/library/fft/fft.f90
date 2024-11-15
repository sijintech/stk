module nmathfft_fft
    implicit none
    interface n_fft_data_set
        module procedure n_fft_int_data_set
        module procedure n_fft_double_data_set
    end interface n_fft_data_set

    interface n_fft_data_get
        module procedure n_fft_double_data_get_3d
        module procedure n_fft_double_data_get_4d
        module procedure n_fft_int_data_get
    end interface n_fft_data_get

    interface n_fft_forward
        module procedure n_fft_r2c_forward_3d
        module procedure n_fft_r2c_forward_n3d
    end interface n_fft_forward

    interface n_fft_backward
        module procedure n_fft_r2c_backward_3d
        module procedure n_fft_r2c_backward_n3d
    end interface n_fft_backward

    interface n_fft_derivative
        module procedure n_fft_r2c_derivative_3d
    end interface n_fft_derivative

    interface
        subroutine n_fft_int_data_set_c(choice,dim) bind(c,name="n_fft_data_int_array_set_f")
            use, intrinsic :: iso_c_binding, only: c_char, c_ptr
            type(c_ptr) :: dim
            character(kind=c_char),intent(in),dimension(*) :: choice
        end subroutine

        subroutine n_fft_double_data_set_c(choice,delta) bind(c,name="n_fft_data_double_array_set_f")
            use, intrinsic :: iso_c_binding, only: c_char, c_ptr
            type(c_ptr) :: delta
            character(kind=c_char),intent(in),dimension(*) :: choice
        end subroutine

        subroutine n_fft_int_data_get_c(choice,data) bind(c, name="n_fft_data_int_array_get_f")
            use, intrinsic :: iso_c_binding, only: c_char, c_ptr
            type(c_ptr) :: data
            character(kind=c_char),intent(in),dimension(*) :: choice
        end subroutine

        subroutine n_fft_double_data_get_c(choice,data) bind(c, name="n_fft_data_double_array_get_f")
            use, intrinsic :: iso_c_binding, only: c_char, c_ptr
            type(c_ptr) :: data
            character(kind=c_char),intent(in),dimension(*) :: choice
        end subroutine

        subroutine n_fft_setup_c(choice) bind(c, name="n_fft_setup_f")
            use, intrinsic :: iso_c_binding, only: c_char, c_ptr
            character(kind=c_char),intent(in),dimension(*) :: choice
        end subroutine

        subroutine n_fft_r2c_forward_c(choice, in, out) bind(c, name="n_fft_r2c_forward_f")
            use, intrinsic :: iso_c_binding, only: c_char, c_ptr
            character(kind=c_char),intent(in),dimension(*) :: choice
            type(c_ptr) :: in
            type(c_ptr) :: out
        end subroutine
    
        subroutine n_fft_r2c_backward_c(choice, in, out) bind(c, name="n_fft_r2c_backward_f")
            use, intrinsic :: iso_c_binding, only: c_char, c_ptr
            character(kind=c_char),intent(in),dimension(*) :: choice
            type(c_ptr) :: in
            type(c_ptr) :: out
        end subroutine

        subroutine n_fft_r2c_derivative_c(choice, in, out) bind(c, name="n_fft_derivative_f")
            use, intrinsic :: iso_c_binding, only: c_char, c_ptr
            character(kind=c_char),intent(in),dimension(*) :: choice
            type(c_ptr) :: in
            type(c_ptr) :: out
        end subroutine
    end interface
    contains

    subroutine n_fft_int_data_set(choice,dim)
        use,intrinsic :: iso_c_binding
        implicit none
        character(len=*),intent(in) :: choice
        character(len=100) :: choice_c
        integer(kind=4), target,dimension(:) :: dim
        choice_c = choice//char(0)
        call n_fft_int_data_set_c(choice_c, c_loc(dim))
    end subroutine

    subroutine n_fft_double_data_set(choice, delta)
        use, intrinsic :: iso_c_binding
        implicit none
        character(len=*), intent(in) :: choice
        character(len=100) :: choice_c
        real(kind=8), target,dimension(:) :: delta
        choice_c = choice//char(0)
        call n_fft_double_data_set_c(choice_c, c_loc(delta))        
    end subroutine

    subroutine n_fft_double_data_get_3d(choice, data)
        use, intrinsic :: iso_c_binding
        implicit none
        character(len=*), intent(in) :: choice
        character(len=100) :: choice_c
        real(kind=8), target,dimension(:,:,:) :: data
        choice_c = choice//char(0)
        call n_fft_double_data_get_c(choice_c, c_loc(data))             
    end subroutine

    subroutine n_fft_double_data_get_4d(choice, data)
        use, intrinsic :: iso_c_binding
        implicit none
        character(len=*), intent(in) :: choice
        character(len=100) :: choice_c
        real(kind=8), target,dimension(:,:,:,:) :: data
        choice_c = choice//char(0)
        call n_fft_double_data_get_c(choice_c, c_loc(data))             
    end subroutine

    subroutine n_fft_int_data_get(choice, data)
        use, intrinsic :: iso_c_binding
        use iso_fortran_env
        implicit none
        character(len=*), intent(in) :: choice
        character(len=100) :: choice_c
        integer(kind=int32), target,dimension(:) :: data
        choice_c = choice//char(0)
        call n_fft_int_data_get_c(choice_c, c_loc(data))             
    end subroutine

    subroutine n_fft_setup(choice)
        use, intrinsic :: iso_c_binding
        implicit none
        character(len=*), intent(in) :: choice
        character(len=100) :: choice_c
        choice_c = choice//char(0)
        call n_fft_setup_c(choice_c)        
    end subroutine  

    subroutine n_fft_r2c_forward_3d(choice, in ,out)
        use, intrinsic :: iso_c_binding
        implicit none
        character(len=*), intent(in) :: choice
        character(len=100) :: choice_c
        real(kind=8), target,dimension(:,:,:) :: in
        complex(kind=8), target, dimension(:,:,:) :: out
        choice_c = choice//char(0)
        call n_fft_r2c_forward_c(choice_c, c_loc(in), c_loc(out))
    end subroutine

    subroutine n_fft_r2c_backward_3d(choice, in, out)
        use, intrinsic :: iso_c_binding
        implicit none
        character(len=*), intent(in) :: choice
        character(len=100) :: choice_c
        real(kind=8), target,dimension(:,:,:) :: out
        complex(kind=8), target, dimension(:,:,:) :: in
        choice_c = choice//char(0)
        call n_fft_r2c_backward_c(choice_c, c_loc(in), c_loc(out))
    end subroutine

    subroutine n_fft_r2c_derivative_3d(choice, in, out)
        use, intrinsic:: iso_c_binding
        implicit none
        character(len=*), intent(in) :: choice
        character(len=100) :: choice_c
        real(kind=8), target,dimension(:,:,:) :: out
        real(kind=8), target, dimension(:,:,:) :: in
        choice_c = choice//char(0)
        call n_fft_r2c_derivative_c(choice_c, c_loc(in), c_loc(out))        
    end subroutine

    subroutine n_fft_r2c_forward_n3d(choice, in ,out)
        use, intrinsic :: iso_c_binding
        implicit none
        character(len=*), intent(in) :: choice
        character(len=100) :: choice_c
        real(kind=8), target,dimension(:,:,:,:) :: in
        complex(kind=8), target, dimension(:,:,:,:) :: out
        choice_c = choice//char(0)
        call n_fft_r2c_forward_c(choice_c, c_loc(in), c_loc(out))
    end subroutine

    subroutine n_fft_r2c_backward_n3d(choice, in, out)
        use, intrinsic :: iso_c_binding
        implicit none
        character(len=*), intent(in) :: choice
        character(len=100) :: choice_c
        real(kind=8), target,dimension(:,:,:,:) :: out
        complex(kind=8), target, dimension(:,:,:,:) :: in
        choice_c = choice//char(0)
        call n_fft_r2c_backward_c(choice_c, c_loc(in), c_loc(out))
    end subroutine
end module