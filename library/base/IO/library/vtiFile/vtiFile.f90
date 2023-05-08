module niobasic_vtifile
    use iso_c_binding
    implicit none

    interface
        subroutine n_vtiFile_4D_double_write_c(x, y, z, c, data, fileName) bind(c,name="n_vtiFile_4D_double_write_f")
            use,intrinsic :: iso_c_binding, only: c_char, c_int, c_ptr
            type(c_ptr),intent(in) :: data
            integer(c_int),intent(in) :: c,x,y,z
            character(kind=c_char),intent(in),dimension(*) :: fileName
        end subroutine

        subroutine n_vtiFile_4D_int_write_c(x, y, z, c, data, fileName) bind(c,name="n_vtiFile_4D_int_write_f")
            use,intrinsic :: iso_c_binding, only: c_char, c_int, c_ptr
            type(c_ptr),intent(in) :: data
            integer(c_int),intent(in) :: c,x,y,z
            character(kind=c_char),intent(in),dimension(*) :: fileName
        end subroutine

        subroutine n_vtiFile_4D_double_read_c(x, y, z, c, data, fileName) bind(c,name="n_vtiFile_4D_double_read_f")
            use,intrinsic :: iso_c_binding, only: c_char, c_int, c_ptr
            type(c_ptr),intent(in) :: data
            integer(c_int),intent(in) :: c,x,y,z
            character(kind=c_char),intent(in),dimension(*) :: fileName
        end subroutine

        subroutine n_vtiFile_4D_int_read_c(x, y, z, c, data, fileName) bind(c,name="n_vtiFile_4D_int_read_f")
            use,intrinsic :: iso_c_binding, only: c_char, c_int, c_ptr
            type(c_ptr),intent(in) :: data
            integer(c_int),intent(in) :: c,x,y,z
            character(kind=c_char),intent(in),dimension(*) :: fileName
        end subroutine

        subroutine n_vtiFile_3D_double_write_c(x, y, z, data, fileName) bind(c,name="n_vtiFile_3D_double_write_f")
            use,intrinsic :: iso_c_binding, only: c_char, c_int, c_ptr
            type(c_ptr),intent(in) :: data
            integer(c_int),intent(in) :: x,y,z
            character(kind=c_char),intent(in),dimension(*) :: fileName
        end subroutine

        subroutine n_vtiFile_3D_int_write_c(x, y, z, data, fileName) bind(c,name="n_vtiFile_3D_int_write_f")
            use,intrinsic :: iso_c_binding, only: c_char, c_int, c_ptr
            type(c_ptr),intent(in) :: data
            integer(c_int),intent(in) :: x,y,z
            character(kind=c_char),intent(in),dimension(*) :: fileName
        end subroutine

        subroutine n_vtiFile_3D_double_read_c(x, y, z, data, fileName) bind(c,name="n_vtiFile_3D_double_read_f")
            use,intrinsic :: iso_c_binding, only: c_char, c_int, c_ptr
            type(c_ptr),intent(in) :: data
            integer(c_int),intent(in) :: x,y,z
            character(kind=c_char),intent(in),dimension(*) :: fileName
        end subroutine

        subroutine n_vtiFile_3D_int_read_c(x, y, z, data, fileName) bind(c,name="n_vtiFile_3D_int_read_f")
            use,intrinsic :: iso_c_binding, only: c_char, c_int, c_ptr
            type(c_ptr),intent(in) :: data
            integer(c_int),intent(in) :: x,y,z
            character(kind=c_char),intent(in),dimension(*) :: fileName
        end subroutine
    end interface

    contains
    subroutine n_vtiFile_4D_double_write(data,filename)
        use,intrinsic :: iso_c_binding
        implicit none
        integer :: x,y,z,c
        real(kind=8),intent(in),target :: data(:,:,:,:)
        character(len=*),intent(in) :: filename
        character(len=100) :: filename_c
        filename_c=filename//char(0)
        x=size(data,4)
        y=size(data,3)
        z=size(data,2)
        c=size(data,1)
        call n_vtiFile_4D_double_write_c(x,y,z,c,c_loc(data),filename_c)
    end subroutine

    subroutine n_vtiFile_4D_int_write(data,filename)
        use,intrinsic :: iso_c_binding
        implicit none
        integer :: x,y,z,c
        integer,intent(in),target :: data(:,:,:,:)
        character(len=*),intent(in) :: filename
        character(len=100) :: filename_c
        filename_c=filename//char(0)
        x=size(data,4)
        y=size(data,3)
        z=size(data,2)
        c=size(data,1)
        call n_vtiFile_4D_int_write_c(x,y,z,c,c_loc(data),filename_c)
    end subroutine

    subroutine n_vtiFile_4D_double_read(data,filename)
        use,intrinsic :: iso_c_binding
        implicit none
        integer :: x,y,z,c
        real(kind=8),intent(inout),target :: data(:,:,:,:)
        character(len=*),intent(in) :: filename
        character(len=100) :: filename_c
        filename_c=filename//char(0)
        x=size(data,4)
        y=size(data,3)
        z=size(data,2)
        c=size(data,1)
        call n_vtiFile_4D_double_read_c(x,y,z,c,c_loc(data),filename_c)
    end subroutine

    subroutine n_vtiFile_4D_int_read(data,filename)
        use,intrinsic :: iso_c_binding
        implicit none
        integer :: x,y,z,c
        integer,intent(inout),target :: data(:,:,:,:)
        character(len=*),intent(in) :: filename
        character(len=100) :: filename_c
        filename_c=filename//char(0)
        x=size(data,4)
        y=size(data,3)
        z=size(data,2)
        c=size(data,1)
        call n_vtiFile_4D_int_read_c(x,y,z,c,c_loc(data),filename_c)
    end subroutine

    subroutine n_vtiFile_3D_double_write(data,filename)
        use,intrinsic :: iso_c_binding
        implicit none
        integer :: x,y,z
        real(kind=8),intent(in),target :: data(:,:,:)
        character(len=*),intent(in) :: filename
        character(len=100) :: filename_c
        filename_c=filename//char(0)
        x=size(data,3)
        y=size(data,2)
        z=size(data,1)
        call n_vtiFile_3D_double_write_c(x,y,z,c_loc(data),filename_c)
    end subroutine

    subroutine n_vtiFile_3D_int_write(data,filename)
        use,intrinsic :: iso_c_binding
        implicit none
        integer :: x,y,z
        integer,intent(in),target :: data(:,:,:)
        character(len=*),intent(in) :: filename
        character(len=100) :: filename_c
        filename_c=filename//char(0)
        x=size(data,3)
        y=size(data,2)
        z=size(data,1)
        call n_vtiFile_3D_int_write_c(x,y,z,c_loc(data),filename_c)
    end subroutine

    subroutine n_vtiFile_3D_double_read(data,filename)
        use,intrinsic :: iso_c_binding
        implicit none
        integer :: x,y,z
        real(kind=8),intent(inout),target :: data(:,:,:)
        character(len=*),intent(in) :: filename
        character(len=100) :: filename_c
        filename_c=filename//char(0)
        x=size(data,3)
        y=size(data,2)
        z=size(data,1)
        call n_vtiFile_3D_double_read_c(x,y,z,c_loc(data),filename_c)
    end subroutine

    subroutine n_vtiFile_3D_int_read(data,filename)
        use,intrinsic :: iso_c_binding
        implicit none
        integer :: x,y,z
        integer,intent(inout),target :: data(:,:,:)
        character(len=*),intent(in) :: filename
        character(len=100) :: filename_c
        filename_c=filename//char(0)
        x=size(data,3)
        y=size(data,2)
        z=size(data,1)
        call n_vtiFile_3D_int_read_c(x,y,z,c_loc(data),filename_c)
    end subroutine
end module