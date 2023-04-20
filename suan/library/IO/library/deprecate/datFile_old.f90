module datFile
    use iso_c_binding
    implicit none

    type,bind(c) :: dat_4d_double
        integer(c_int) dim1,dim2,dim3,component
        type(c_ptr):: data
    end type dat_4d_double

    type,bind(c) :: dat_4d_int
        integer(c_int) dim1,dim2,dim3,component
        type(c_ptr):: data
    end type dat_4d_int
    interface
        subroutine datfile_4d_double_read_c(datatype,filename) bind(c,name="DatFile_4D_double_read")
            use,intrinsic :: iso_c_binding, only: c_char
            Import :: dat_4d_double
            character(kind=c_char),intent(in),dimension(*) :: filename
            type(dat_4d_double),intent(inout) :: datatype
        end subroutine

        subroutine datfile_4d_int_read_c(datatype,filename) bind(c,name="DatFile_4D_int_read")
            use,intrinsic :: iso_c_binding, only: c_char
            Import :: dat_4d_int
            character(kind=c_char),intent(in),dimension(*) :: filename
            type(dat_4d_int),intent(inout) :: datatype
        end subroutine
    end interface


    contains

    subroutine DatFile_4D_double_read(input,filename)
        use,intrinsic :: iso_c_binding, only:c_double
        implicit none
        real(kind=8),intent(inout),target::input(:,:,:,:)
        character(len=*),intent(in) :: filename
        character(len=100) :: filename_c
        type(dat_4d_double) :: da
        da%dim1=size(input,4)
        da%dim2=size(input,3)
        da%dim3=size(input,2)
        da%component=size(input,1)
        ! print *,"da",da%dim1,da%dim2,da%dim3,da%component
        filename_c=filename//char(0)
        da%data=c_loc(input)
        call datfile_4d_double_read_c(da,filename_c)
    end subroutine

    subroutine DatFile_4D_int_read(input,filename)
        use,intrinsic :: iso_c_binding, only:c_int
        implicit none
        integer,intent(inout),target::input(:,:,:,:)
        character(len=*),intent(in) :: filename
        character(len=100) :: filename_c
        type(dat_4d_int) :: da
        da%dim1=size(input,4)
        da%dim2=size(input,3)
        da%dim3=size(input,2)
        da%component=size(input,1)
        ! print *,"da",da%dim1,da%dim2,da%dim3,da%component
        filename_c=filename//char(0)
        da%data=c_loc(input)
        call datfile_4d_int_read_c(da,filename_c)
    end subroutine
end module