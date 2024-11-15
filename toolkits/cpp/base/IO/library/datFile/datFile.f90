module niobasic_datFile
    use iso_c_binding
    implicit none

    interface
        subroutine n_datFile_4D_int_read_c(x,y,z,c,data,filename) bind(c,name="n_datFile_4D_int_read_f")
            use,intrinsic :: iso_c_binding, only: c_char,c_int,c_ptr
            character(kind=c_char),intent(in),dimension(*) :: filename
            integer(kind=c_int),intent(in) :: x,y,z,c
            type(c_ptr) :: data
        end subroutine

        subroutine n_datFile_3D_int_read_c(x,y,z,data,filename) bind(c,name="n_datFile_3D_int_read_f")
            use,intrinsic :: iso_c_binding, only: c_char,c_int,c_ptr
            character(kind=c_char),intent(in),dimension(*) :: filename
            integer(kind=c_int),intent(in) :: x,y,z
            type(c_ptr) :: data
        end subroutine

        subroutine n_datFile_4D_double_read_c(x,y,z,c,data,filename) bind(c,name="n_datFile_4D_double_read_f")
            use,intrinsic :: iso_c_binding, only: c_char,c_int,c_ptr
            character(kind=c_char),intent(in),dimension(*) :: filename
            integer(kind=c_int),intent(in) :: x,y,z,c
            type(c_ptr) :: data
        end subroutine

        subroutine n_datFile_3D_double_read_c(x,y,z,data,filename) bind(c,name="n_datFile_3D_double_read_f")
            use,intrinsic :: iso_c_binding, only: c_char,c_int,c_ptr
            character(kind=c_char),intent(in),dimension(*) :: filename
            integer(kind=c_int),intent(in) :: x,y,z
            type(c_ptr) :: data
        end subroutine


    subroutine n_datFile_4D_int_write_c(x,y,z,c,data,filename) bind(c,name="n_datFile_4D_int_write_f")
        use,intrinsic :: iso_c_binding, only: c_char,c_int,c_ptr
        character(kind=c_char),intent(in),dimension(*) :: filename
        integer(kind=c_int),intent(in) :: x,y,z,c
        type(c_ptr) :: data
    end subroutine

    subroutine n_datFile_3D_int_write_c(x,y,z,data,filename) bind(c,name="n_datFile_3D_int_write_f")
        use,intrinsic :: iso_c_binding, only: c_char,c_int,c_ptr
        character(kind=c_char),intent(in),dimension(*) :: filename
        integer(kind=c_int),intent(in) :: x,y,z
        type(c_ptr) :: data
    end subroutine

    subroutine n_datFile_4D_double_write_c(x,y,z,c,data,filename) bind(c,name="n_datFile_4D_double_write_f")
        use,intrinsic :: iso_c_binding, only: c_char,c_int,c_ptr
        character(kind=c_char),intent(in),dimension(*) :: filename
        integer(kind=c_int),intent(in) :: x,y,z,c
        type(c_ptr) :: data
    end subroutine

    subroutine n_datFile_3D_double_write_c(x,y,z,data,filename) bind(c,name="n_datFile_3D_double_write_f")
        use,intrinsic :: iso_c_binding, only: c_char,c_int,c_ptr
        character(kind=c_char),intent(in),dimension(*) :: filename
        integer(kind=c_int),intent(in) :: x,y,z
        type(c_ptr) :: data
    end subroutine
end interface
    contains

    subroutine n_datFile_4D_int_read(input,filename)
        use,intrinsic :: iso_c_binding, only:c_int
        implicit none
        integer,intent(out),target::input(:,:,:,:)
        character(len=*),intent(in) :: filename
        character(len=100) :: filename_c
        integer :: x,y,z,c
        x=size(input,4)
        y=size(input,3)
        z=size(input,2)
        c=size(input,1)
        ! print *,"da",da%dim1,da%dim2,da%dim3,da%component
        filename_c=filename//char(0)
        call n_datFile_4D_int_read_c(x,y,z,c,c_loc(input),filename_c)
    end subroutine

    subroutine n_datFile_3D_int_read(input,filename)
        use,intrinsic :: iso_c_binding, only:c_int
        implicit none
        integer,intent(out),target::input(:,:,:)
        character(len=*),intent(in) :: filename
        character(len=100) :: filename_c
        integer :: x,y,z
        x=size(input,3)
        y=size(input,2)
        z=size(input,1)
        ! print *,"da",da%dim1,da%dim2,da%dim3,da%component
        filename_c=filename//char(0)
        call n_datFile_3D_int_read_c(x,y,z,c_loc(input),filename_c)
    end subroutine

    subroutine n_datFile_4D_double_read(input,filename)
        use,intrinsic :: iso_c_binding, only:c_double
        implicit none
        real(kind=8),intent(out),target::input(:,:,:,:)
        character(len=*),intent(in) :: filename
        character(len=100) :: filename_c
        integer :: x,y,z,c
        x=size(input,4)
        y=size(input,3)
        z=size(input,2)
        c=size(input,1)
        ! print *,"da",da%dim1,da%dim2,da%dim3,da%component
        filename_c=filename//char(0)
        call n_datFile_4D_double_read_c(x,y,z,c,c_loc(input),filename_c)
    end subroutine

    subroutine n_datFile_3D_double_read(input,filename)
        use,intrinsic :: iso_c_binding, only:c_double
        implicit none
        real(kind=8),intent(out),target::input(:,:,:)
        character(len=*),intent(in) :: filename
        character(len=100) :: filename_c
        integer :: x,y,z
        x=size(input,3)
        y=size(input,2)
        z=size(input,1)
        ! print *,"da",da%dim1,da%dim2,da%dim3,da%component
        filename_c=filename//char(0)
        call n_datFile_3D_double_read_c(x,y,z,c_loc(input),filename_c)
    end subroutine



    subroutine n_datFile_4D_int_write(input,filename)
        use,intrinsic :: iso_c_binding, only:c_int
        implicit none
        integer,intent(in),target::input(:,:,:,:)
        character(len=*),intent(in) :: filename
        character(len=100) :: filename_c
        integer :: x,y,z,c
        x=size(input,4)
        y=size(input,3)
        z=size(input,2)
        c=size(input,1)
        ! print *,"da",da%dim1,da%dim2,da%dim3,da%component
        filename_c=filename//char(0)
        call n_datFile_4D_int_write_c(x,y,z,c,c_loc(input),filename_c)
    end subroutine

    subroutine n_datFile_3D_int_write(input,filename)
        use,intrinsic :: iso_c_binding, only:c_int
        implicit none
        integer,intent(in),target::input(:,:,:)
        character(len=*),intent(in) :: filename
        character(len=100) :: filename_c
        integer :: x,y,z
        x=size(input,3)
        y=size(input,2)
        z=size(input,1)
        ! print *,"da",da%dim1,da%dim2,da%dim3,da%component
        filename_c=filename//char(0)
        call n_datFile_3D_int_write_c(x,y,z,c_loc(input),filename_c)
    end subroutine

    subroutine n_datFile_4D_double_write(input,filename)
        use,intrinsic :: iso_c_binding, only:c_double
        implicit none
        real(kind=8),intent(in),target::input(:,:,:,:)
        character(len=*),intent(in) :: filename
        character(len=100) :: filename_c
        integer :: x,y,z,c
        x=size(input,4)
        y=size(input,3)
        z=size(input,2)
        c=size(input,1)
        ! print *,"da",da%dim1,da%dim2,da%dim3,da%component
        filename_c=filename//char(0)
        call n_datFile_4D_double_write_c(x,y,z,c,c_loc(input),filename_c)
    end subroutine

    subroutine n_datFile_3D_double_write(input,filename)
        use,intrinsic :: iso_c_binding, only:c_double
        implicit none
        real(kind=8),intent(in),target::input(:,:,:)
        character(len=*),intent(in) :: filename
        character(len=100) :: filename_c
        integer :: x,y,z
        x=size(input,3)
        y=size(input,2)
        z=size(input,1)
        ! print *,"da",da%dim1,da%dim2,da%dim3,da%component
        filename_c=filename//char(0)
        call n_datFile_3D_double_write_c(x,y,z,c_loc(input),filename_c)
    end subroutine
end module