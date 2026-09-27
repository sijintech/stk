module quantification_3d
    use iso_c_binding
    implicit none 
    interface
    subroutine hetero3D(ppt,s_eta, ave_f,ave_tri,ave_quad,ave_gb_area)
        ! use global
        implicit none
        integer,dimension(:,:,:),intent(in) :: ppt
        real,intent(in),dimension(:,:,:) :: s_eta
        real,intent(out) :: ave_f,ave_tri,ave_quad, ave_gb_area
    end subroutine

    subroutine push_fstack(m1,m2)
        ! use global
        implicit none
        integer,intent(in) :: m1,m2
    end subroutine

    subroutine push_tristack(m1,m2,m3)
        ! use global
        implicit none
        integer,intent(in) :: m1,m2,m3
    end subroutine 

    subroutine push_quadstack(g1,g2,g3,g4,x,y,z,s_eta)
        ! use global
        implicit none
        integer,intent(inout) :: g1,g2,g3,g4
        integer,intent(in)::x,y,z
        real,intent(in),dimension(:,:,:) :: s_eta
    end subroutine

    subroutine push_removestack(idx)
        ! use global
        implicit none
        integer,intent(in) :: idx
    end subroutine

    subroutine pop_removestack(rtri_idx)
        ! use global
        implicit none
        integer,intent(out) :: rtri_idx 
    end subroutine

    subroutine prepare_neigh(i,j,k, neigh)
        ! use global
        implicit none
        integer,intent(in) :: i,j,k
        integer, intent(out),dimension(26,3) :: neigh
    end subroutine

    subroutine Quant3D(eta,s_eta,ppt,nop,gid,istep,ave_vol,ave_rad, ave_f,ave_tri,ave_quad, ave_gb_area)
        implicit none
        real,intent(in),dimension(:,:,:) :: s_eta
        integer,intent(in),dimension(:,:,:,:) :: gid
        integer,intent(in),dimension(:,:,:) :: nop,ppt
        real,intent(in),dimension(:,:,:,:) :: eta
        real,intent(out) :: ave_vol, ave_rad, ave_f,ave_tri,ave_quad, ave_gb_area
        integer, intent(in) :: istep
    end subroutine

    subroutine gvol_out(filename)
        ! use global
        implicit none
        character(len=*),intent(in) :: filename
    end subroutine

    subroutine gbarea_out(filename)
        ! use global
        implicit none
        character(len=*),intent(in) ::  filename
    end subroutine

    end interface

    integer :: nx, ny, nz, no !from outside

    integer :: nf, ntri, nquad, ridx, ng
    ! integer :: vol_spher, vol_plate_1, vol_plate_2, vol_plate_3, vol_plate_max,con_plate,nplate
    real,parameter :: pi_math=atan(1.0)*4.0
    ! real,parameter :: rad_spher = 5.0
    ! real,parameter :: maxbin=3.0,minbin=0.0,bin=0.1
    real :: maxbin, minbin, bin, dt, dx
    integer :: nbin
    integer :: maxnn !Maximum number of neighboring grains in 3D
    integer :: maxtj !Maximum number of triple junctions
    integer :: maxqj !Maximum number of quadruple junctions
    
    integer :: maxgbarea !Maximum area of grain boundary
    real,allocatable,dimension(:) :: vol,g_rad,gdist,fdist,gbdist,tjdist,qjdist
    integer,dimension(:,:,:),allocatable:: map, map2
    integer,dimension(:),allocatable :: xn, xp, yn, yp, zn, zp
    integer,dimension(:,:),allocatable :: fstack,tristack,quadstack, quadpos
    integer,dimension(:),allocatable :: fidx,removestack
    integer,dimension(:),allocatable :: g_f,g_tj, g_qj
    ! integer,dimension(:,:),allocatable :: v_grain_list,v_grain_area
    ! integer,dimension(:),allocatable :: n_v_grain

    contains
    subroutine initiate_quantification_3d(x,y,z,o,t,ddx,maxb,minb,b,maxn,maxt,maxq)
        use niobasic_timefile
        implicit none
        integer,intent(in) :: x,y,z,o
        real,intent(in) :: t, ddx
        real,intent(in),optional::maxb,minb,b
        integer,intent(in),optional::maxn,maxt,maxq
        integer :: i,j,k
        nx = x
        ny = y
        nz = z
        no = o
        dt = t
        dx = ddx
        if(present(maxb))then   
            maxbin=maxb
        else
            maxbin=3.0
        endif
        if(present(minb))then
            minbin=minb
        else
            minbin=0.0
        endif
        if(present(b))then
            bin=b
        else
            bin = 0.1
        endif

        if(present(maxn))then
            maxnn=maxn
        else
            maxnn = 30
        endif
        if(present(maxt))then
            maxtj=maxt
        else
            maxtj = 70
        endif
        if(present(maxq))then
            maxqj=maxq
        else
            maxqj = 60
        endif   
        
        nbin=anint((maxbin-minbin)/bin)
        maxgbarea=nx*ny/2

        allocate(xn(nx))
        allocate(xp(nx))
        allocate(yn(ny))
        allocate(yp(ny))
        allocate(zn(nz))
        allocate(zp(nz))

        allocate(fstack(no*10,2),fidx(no*10))
        allocate(tristack(no*30,3))
        allocate(quadstack(no*20,4))
        allocate(quadpos(no*20,3))
        allocate(removestack(10))

        allocate(gdist(nbin))
        allocate(gbdist(maxgbarea))
        allocate(fdist(maxnn))

        allocate(map(nx,ny,nz),map2(nx,ny,nz))
        allocate(vol(no),g_rad(no))
        allocate(g_f(no),g_tj(no),g_qj(no))
        allocate(tjdist(maxtj),qjdist(maxqj))

        xn(1)=2
        xp(1)=nx
        do i=2,nx
          xn(i)=i+1
          xp(i)=i-1
        enddo
        xn(nx)=1
        xp(nx)=nx-1
      
        yn(1)=2
        yp(1)=ny
        do j=2,ny
          yn(j)=j+1
          yp(j)=j-1
        enddo
        yn(ny)=1
        yp(ny)=ny-1
      
        zn(1)=2
        zp(1)=nz
        do k=2,nz
          zn(k)=k+1
          zp(k)=k-1
        enddo
        zn(nz)=1
        zp(nz)=nz-1

        call n_timeFile_write_line_from_string("time, ave_rad, ave_vol,ave_f,ave_gb_area, ave_tri, ave_quad, ng", "mquant_t.csv")
        call n_timeFile_write_line_from_string("step,ng,bin,gdist,sqrt(gdist)","gsize_dist.csv")
        call n_timeFile_write_line_from_string("step,ng,neighbour_grain_index,fdist,sqrt_fdist","face_dist.csv")
        call n_timeFile_write_line_from_string("step,ng,triple_junction_index,tjdist,sqrt_tjdist","tj_dist.csv")
        call n_timeFile_write_line_from_string("step,ng,quadruple_junction_index,qjdist,sqrt_qjdist","qj_dist.csv")
        call n_timeFile_write_line_from_string("step,nf,gb_area_index,gbdist,sqrt_gbdist","gb_area_dist.csv")
    end subroutine

    subroutine destruct_quantification_3d
        implicit none

        deallocate(xn)
        deallocate(xp)
        deallocate(yn)
        deallocate(yp)
        deallocate(zn)
        deallocate(zp)

        deallocate(fstack,fidx)
        deallocate(tristack)
        deallocate(quadstack)
        deallocate(quadpos)
        deallocate(removestack)

        deallocate(gdist)
        deallocate(gbdist)
        deallocate(fdist)

        deallocate(map,map2)
        deallocate(vol,g_rad)
        deallocate(g_f,g_tj,g_qj)
        deallocate(tjdist,qjdist) 
    end subroutine

end module