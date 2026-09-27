module structureGenerator
    use iso_c_binding
    implicit none
    interface
        subroutine n_generate_structure_from_file_c(x,y,z,data,fileName, path) bind(c,name="n_generate_structure_from_file_f")
            use,intrinsic:: iso_c_binding, only: c_char, c_int, c_ptr
            type(c_ptr),intent(in) :: data
            integer(c_int),intent(in) :: x,y,z
            character(kind=c_char),intent(in),dimension(*) :: fileName, path
        end subroutine
        subroutine n_structure_assign_data_c(x,y,z,c,data,structure,compare,assignValue) bind(c,name="n_structure_assign_data_f")
            use,intrinsic::iso_c_binding, only: c_char, c_int, c_ptr
            type(c_ptr),intent(in) :: data
            type(c_ptr), intent(in) :: structure,assignValue
            integer(c_int),intent(in) :: x,y,z,c,compare
        end subroutine
        subroutine n_material_generator_c(tensor,filename,xpath,tensorname) bind(c,name="n_material_generator_f")
            use,intrinsic::iso_c_binding, only:c_char, c_ptr
            type(c_ptr), intent(in) :: tensor
            character(kind=c_char),intent(in),dimension(*) :: filename,xpath,tensorname
        end subroutine
        subroutine n_material_generator_one_phase_c(tensor,filename,xpath,tensorname)bind(c,name="n_material_generator_one_phase_f")
            use,intrinsic::iso_c_binding, only:c_char, c_ptr
            type(c_ptr), intent(in) :: tensor
            character(kind=c_char),intent(in),dimension(*) :: filename,xpath,tensorname
        end subroutine    
    end interface

    contains
    subroutine n_material_generator_rank2(tensor,filename,xpath,tensorname) 
        use,intrinsic :: iso_c_binding
        implicit none
        real(kind=8),intent(in),target :: tensor(:,:,:)
        character(len=*),intent(in) :: filename,xpath,tensorname
        character(len=100) :: filename_c,xpath_c,tensorname_c
        filename_c=filename//char(0)
        xpath_c=xpath//char(0)
        tensorname_c=tensorname//char(0)
        call n_material_generator_c(c_loc(tensor),filename_c,xpath_c,tensorname_c)
    end subroutine

    subroutine n_material_generator_rank1(tensor,filename,xpath,tensorname) 
        use,intrinsic :: iso_c_binding
        implicit none
        real(kind=8),intent(in),target :: tensor(:,:)
        character(len=*),intent(in) :: filename,xpath,tensorname
        character(len=100) :: filename_c,xpath_c,tensorname_c
        filename_c=filename//char(0)
        xpath_c=xpath//char(0)
        tensorname_c=tensorname//char(0)
        call n_material_generator_c(c_loc(tensor),filename_c,xpath_c,tensorname_c)
    end subroutine

    subroutine n_material_generator_rank0(tensor,filename,xpath,tensorname) 
        use,intrinsic :: iso_c_binding
        implicit none
        real(kind=8),intent(in),target :: tensor(:)
        character(len=*),intent(in) :: filename,xpath,tensorname
        character(len=100) :: filename_c,xpath_c,tensorname_c
        filename_c=filename//char(0)
        xpath_c=xpath//char(0)
        tensorname_c=tensorname//char(0)
        call n_material_generator_c(c_loc(tensor),filename_c,xpath_c,tensorname_c)
    end subroutine

    subroutine n_material_generator_one_phase_rank2(tensor,filename,xpath,tensorname) 
        use,intrinsic :: iso_c_binding
        implicit none
        real(kind=8),intent(in),target :: tensor(:,:)
        character(len=*),intent(in) :: filename,xpath,tensorname
        character(len=100) :: filename_c,xpath_c,tensorname_c
        filename_c=filename//char(0)
        xpath_c=xpath//char(0)
        tensorname_c=tensorname//char(0)
        call n_material_generator_one_phase_c(c_loc(tensor),filename_c,xpath_c,tensorname_c)
    end subroutine

    subroutine n_generate_structure_from_file(data,fileName,path)
        use,intrinsic :: iso_c_binding
        implicit none
        integer :: x,y,z
        integer(kind=2),intent(in),target :: data(:,:,:)
        character(len=*),intent(in) :: filename,path
        character(len=100) :: filename_c,path_c
        filename_c=filename//char(0)
        path_c=path//char(0)
        x=size(data,3)
        y=size(data,2)
        z=size(data,1)
        call n_generate_structure_from_file_c(x,y,z,c_loc(data),filename_c,path_c)
    end subroutine

    subroutine n_structure_assign_data_rank2(data,structure,compare,assignValue)
        use,intrinsic :: iso_c_binding
        use iso_fortran_env
        implicit none
        integer :: x,y,z,c1,c2
        real(kind=8),intent(in),target :: data(:,:,:,:,:),assignValue(:,:)
        integer(kind=2),intent(in),target :: structure(:,:,:)
        integer(kind=int32),intent(in) :: compare

        x=size(data,5)
        y=size(data,4)
        z=size(data,3)
        c1=size(data,2)
        c2=size(data,1)
        if ( c1*c2 .ne. size(assignValue,1)*size(assignValue,2) ) then
            print *,"Your assign value size is not compatible with the array."
        end if
        call n_structure_assign_data_c(x,y,z,c1*c2,c_loc(data),c_loc(structure),compare,c_loc(assignValue))
    end subroutine

    subroutine n_structure_assign_data_rank1(data,structure,compare,assignValue)
        use,intrinsic :: iso_c_binding
        implicit none
        integer :: x,y,z,c
        real(kind=8),intent(in),target :: data(:,:,:,:),assignValue(:)
        integer(kind=2),intent(in),target :: structure(:,:,:)
        integer,intent(in) :: compare

        x=size(data,4)
        y=size(data,3)
        z=size(data,2)
        c=size(data,1)
        call n_structure_assign_data_c(x,y,z,c,c_loc(data),c_loc(structure),compare,c_loc(assignValue))
    end subroutine

    subroutine n_structure_assign_data_rank0(data,structure,compare,assignValue)
        use,intrinsic :: iso_c_binding
        implicit none
        integer :: x,y,z,c
        real(kind=8),intent(in),target :: data(:,:,:),assignValue(1)
        integer(kind=2),intent(in),target :: structure(:,:,:)
        integer,intent(in) :: compare

        x=size(data,3)
        y=size(data,2)
        z=size(data,1)
        c=1
        call n_structure_assign_data_c(x,y,z,c,c_loc(data),c_loc(structure),compare,c_loc(assignValue))
    end subroutine
end module