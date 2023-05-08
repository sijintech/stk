!Program to quantify the microstructure
!Code written at May 23rd 2018
!Major revision at June 10th 2018
!Code written by Kunok Chang (kunok.chang@khu.ac.kr)

subroutine Quant2D
  use global
  implicit none
  real :: rnd,r,maxeta
  integer :: i,j,l,rint

  ng=0
  map=0
  area=0.0
  g_rad=0.0

!$omp parallel do private(i,maxeta,l) shared(area,ng)
  do j=1,ny
  do i=1,nx
    maxeta=maxval(eta(1:nop(i,j),i,j))
    do l=1,nop(i,j)
      if (eta(l,i,j).eq.maxeta) then
        map2(i,j)=gid(l,i,j)
        if (s_eta(i,j).ge.0.8) then
          map(i,j)=gid(l,i,j)
!$omp critical
          area(gid(l,i,j))=area(gid(l,i,j))+1.0
          if (area(gid(l,i,j)).eq.1.0) ng=ng+1
!$omp end critical
        endif
      endif
    enddo
  enddo
  enddo
!$omp end parallel do

  g_rad=sqrt(area/pi_math)

  tot_area=sum(area)
  ave_area=tot_area/ng

  tot_rad=sum(g_rad)
  ave_rad=sum(g_rad)/ng

  gdist=0.0

  do i=1,no
    if (area(i).ge.1.0) then
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

  write(202,102) istep,ng
  do i=1,nbin
    write(202,103) i*bin+bin/2.0,gdist(i)/ng,sqrt(gdist(i))/ng
  enddo

  call initiate_tristack
  call initiate_quadstack
  call initiate_fstack
  call hetero2D

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

  write(203,102) istep,ng
  write(204,102) istep,ng
  write(205,102) istep,ng
  write(206,105) istep,nf
  do i=1,maxnn
    if (fdist(i).ge.1.0) then
      write(203,104) i,fdist(i)/(2.0*nf),sqrt(fdist(i))/(2.0*nf)
    endif
    if (tjdist(i).ge.1.0) then
      write(204,104) i,tjdist(i)/(3.0*ntri),sqrt(tjdist(i))/(3.0*ntri)
    endif
    if (qjdist(i).ge.1.0) then
      write(205,104) i,qjdist(i)/(4.0*nquad),sqrt(qjdist(i))/(4.0*nquad)
    endif
  enddo

  do i=1,maxgblength
    if (gbdist(i).ge.1.0) then
      write(206,104) i,gbdist(i)/nf,sqrt(gbdist(i))/nf
    endif
  enddo

102 format ('When ',i10,' steps, # of grains: ',i10)
103 format (f7.3,' ',f10.5,' ',f8.5)
104 format (i3,' ',f10.5,' ',f8.5)
105 format ('When ',i10,' steps, # of faces: ',i10)

end

subroutine garea_out(filename)
  use global
  implicit none
  character(len=*) filename
  integer :: i,j,l

  open(unit=20,file=filename(:5)//'.garea')

  do i=1,no
    if (area(i).ge.1.0) then
      write(20,101) i,area(i)
    endif
  enddo

  close(20)

101 format (i6,' ',f7.2)

end

subroutine gblength_out(filename)
  use global
  implicit none
  character(len=*) filename
  integer :: i,j,l

  open(unit=20,file=filename(:5)//'.gble')

  do i=1,nf
    write(20,101) fstack(i,1),fstack(i,2),fidx(i)
  enddo

  close(20)

101 format (i6,' ',i6,' ',i3)

end


