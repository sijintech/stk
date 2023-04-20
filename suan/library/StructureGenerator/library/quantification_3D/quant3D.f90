!Program to quantify the microstructure
!Code written at May 23rd 2018
!Major revision at June 10th 2018
!Code written by Kunok Chang (kunok.chang@khu.ac.kr)

subroutine Quant3D(eta,s_eta,ppt,nop,gid,istep,ave_vol,ave_rad, ave_f,ave_tri,ave_quad, ave_gb_area)
  use quantification_3d, quant3d_from_self => quant3d
  use niobasic_timefile
  implicit none
  real,intent(in),dimension(:,:,:) :: s_eta
  integer,intent(in),dimension(:,:,:,:) :: gid
  integer,intent(in),dimension(:,:,:) :: nop,ppt
  real,intent(in),dimension(:,:,:,:) :: eta
  real,intent(out) :: ave_vol, ave_rad, ave_f,ave_tri,ave_quad, ave_gb_area
  integer, intent(in) :: istep
  real :: rnd,r,maxeta
  integer :: i,j,k,l,rint

  ng=0
  map=0
  map2=0
  vol=0.0
  g_rad=0.0

!$omp parallel do private(j,i,maxeta,l) shared(vol,ng)
  do k=1,nz
  do j=1,ny
  do i=1,nx
    maxeta=maxval(eta(1:nop(i,j,k),i,j,k))
    do l=1,nop(i,j,k)
      if (eta(l,i,j,k).eq.maxeta) then
        map2(i,j,k)=gid(l,i,j,k)
        if (s_eta(i,j,k).ge.0.9) then
          map(i,j,k)=gid(l,i,j,k)
!$omp critical
          vol(gid(l,i,j,k))=vol(gid(l,i,j,k))+1.0
          if (vol(gid(l,i,j,k)).eq.1.0) ng=ng+1
!$omp end critical
        endif
      endif
    enddo
  enddo
  enddo
  enddo
!$omp end parallel do

  g_rad=((3.0*vol)/(4.0*pi_math))**(1.0/3.0)

  ! tot_vol=sum(vol)
  ave_vol=sum(vol)/ng

  ! tot_rad=sum(g_rad)
  ave_rad=sum(g_rad)/ng

  gdist=0.0

  do i=1,no
    if (vol(i).ge.1.0) then
      j=aint(g_rad(i)/(bin*ave_rad))
      if (j.gt.nbin) then
        write(*,*) 'Too large grain:',j,nbin
        stop
      endif
      if (j.gt.0) then
        gdist(j)=gdist(j)+1.0
      endif
    endif
  enddo

  ! write(202,102) istep,ng
  do i=1,nbin
    ! write(202,103) i*bin+bin/2.0,gdist(i)/ng,sqrt(gdist(i))/ng
    call n_timeFile_write_line_from_double((/dble(istep),dble(ng),dble(i*bin+bin/2.0), &
            dble(gdist(i)/ng),dble(sqrt(gdist(i))/ng) /),"gsize_dist.csv")
  enddo

  call initiate_tristack
  call initiate_quadstack
  call initiate_fstack
  call hetero3D(ppt,s_eta, ave_f,ave_tri,ave_quad,ave_gb_area)

  g_f=0
  g_tj=0
  g_qj=0
  gbdist=0.0

  do i=1,nf
    g_f(fstack(i,1))=g_f(fstack(i,1))+1
    g_f(fstack(i,2))=g_f(fstack(i,2))+1
    gbdist(fidx(i))=gbdist(fidx(i))+1.0
  enddo

  do i=1,ntri
    g_tj(tristack(i,1))=g_tj(tristack(i,1))+1
    g_tj(tristack(i,2))=g_tj(tristack(i,2))+1
    g_tj(tristack(i,3))=g_tj(tristack(i,3))+1
  enddo

  do i=1,nquad
    g_qj(quadstack(i,1))=g_qj(quadstack(i,1))+1
    g_qj(quadstack(i,2))=g_qj(quadstack(i,2))+1
    g_qj(quadstack(i,3))=g_qj(quadstack(i,3))+1
    g_qj(quadstack(i,4))=g_qj(quadstack(i,4))+1
  enddo

  fdist=0.0
  tjdist=0.0
  qjdist=0.0
  do i=1,no
    if (g_f(i).ne.0) then
      fdist(g_f(i))=fdist(g_f(i))+1.0
    endif
    if (g_tj(i).ne.0) then
      tjdist(g_tj(i))=tjdist(g_tj(i))+1.0
    endif
    if (g_qj(i).ne.0) then
      qjdist(g_qj(i))=qjdist(g_qj(i))+1.0
    endif
  enddo

  ! write(203,102) istep,ng
  ! write(204,102) istep,ng
  ! write(205,102) istep,ng
  ! write(206,105) istep,nf
  do i=1,maxnn
    if (fdist(i).ge.1.0) then
      ! write(203,104) i,fdist(i)/(2.0*nf),sqrt(fdist(i))/(2.0*nf)
      call n_timeFile_write_line_from_double((/dble(istep),dble(ng),&
      dble(i),dble(fdist(i)/(2.0*nf)),dble(sqrt(fdist(i))/(2.0*nf))/),"face_dist.csv")
    endif
  enddo
  do i=1,maxtj
    if (tjdist(i).ge.1.0) then
      ! write(204,104) i,tjdist(i)/(3.0*ntri),sqrt(tjdist(i))/(3.0*ntri)
      call n_timeFile_write_line_from_double((/dble(istep),dble(ng),&
      dble(i),dble(tjdist(i)/(3.0*ntri)),dble(sqrt(tjdist(i))/(3.0*ntri)) /),"tj_dist.csv")
    endif
  enddo
  do i=1,maxqj
    if (qjdist(i).ge.1.0) then
      ! write(205,104) i,qjdist(i)/(4.0*nquad),sqrt(qjdist(i))/(4.0*nquad)
      call n_timeFile_write_line_from_double((/dble(istep),dble(ng),&
      dble(i),dble(qjdist(i)/(4.0*nquad)),dble(sqrt(qjdist(i))/(4.0*nquad)) /),"qj_dist.csv")
    endif
  enddo

  do i=1,maxgbarea
    if (gbdist(i).ge.1.0) then
      ! write(206,106) i,gbdist(i)/nf,sqrt(gbdist(i))/nf
      call n_timeFile_write_line_from_double((/dble(istep),dble(ng),&
      dble(i),dble(gbdist(i)/nf),dble(sqrt(gbdist(i))/nf) /),"gb_area_dist.csv")
    endif
  enddo

! 102 format ('When ',i10,' steps, # of grains: ',i10)
! 103 format (f7.3,' ',f10.5,' ',f8.5)
! 104 format (i6,' ',f12.5,' ',f10.5)
! 105 format ('When ',i10,' steps, # of faces: ',i10)
! 106 format (i6,' ',f12.6,' ',f10.6)

  call n_timeFile_write_line_from_double((/dble(istep*dt),dble(ave_rad*dx),dble(ave_vol*dx**3),&
  dble(ave_f),dble(ave_gb_area*dx*dx),dble(ave_tri),dble(ave_quad),dble(ng)/),"mquant_t.csv")

  write(*,101) istep*dt,ave_rad*dx,ave_vol*dx**3,ave_f,ave_gb_area*dx*dx,ave_tri,ave_quad,ng

  101 format(f10.3,' ',f9.3,' ',f11.3,' ',f6.3,' ',f8.3,' ',f6.3,' ',f6.3,' ',i9)
end

subroutine gvol_out(filename)
  ! use global
  use quantification_3d, gvol_out_from_self => gvol_out
  implicit none
  character(len=*),intent(in) :: filename
  integer :: i,j,l

  open(unit=20,file=filename(:5)//'.gvol')

  do i=1,no
    if (vol(i).ge.1.0) then
      write(20,101) i,vol(i)
    endif
  enddo

  close(20)

101 format (i6,' ',f11.2)

end

subroutine gbarea_out(filename)
  ! use global
  use quantification_3d, gbarea_out_from_self => gbarea_out
  implicit none
  character(len=*),intent(in) ::  filename
  integer :: i,j,l

  open(unit=20,file=filename(:5)//'.gble')

  do i=1,nf
    write(20,101) fstack(i,1),fstack(i,2),fidx(i)
  enddo

  close(20)

101 format (i6,' ',i6,' ',i5)

end
