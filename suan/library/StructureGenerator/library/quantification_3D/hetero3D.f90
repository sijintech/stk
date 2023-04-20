!Program to quantify the face
!Code written at June 11th 2018
!Code written by Kunok Chang (kunok.chang@khu.ac.kr)

! nx, ny, nz
! map mapping data 
! ppt
! map2
! neigh
subroutine hetero3D(ppt,s_eta,ave_f,ave_tri,ave_quad,ave_gb_area)
  ! use global
  ! use quantification_3d,only:prepare_neigh,push_fstack,push_tristack,push_quadstack
  use quantification_3d,hetero3D_from_self => hetero3D
  implicit none
  integer,dimension(:,:,:),intent(in) :: ppt
  real,intent(in),dimension(:,:,:) :: s_eta
  real,intent(out) :: ave_f,ave_tri,ave_quad, ave_gb_area

  integer :: i,j,k,l,m
  integer :: j_lab(8),j_idx,nnmap2,isexist
  integer :: neigh(26,3)

  ridx=0

  do k=1,nz
  do j=1,ny
  do i=1,nx
    call prepare_neigh(i,j,k,neigh)
    j_idx=0
    j_lab=0
    if (map(i,j,k).eq.0.and.ppt(i,j,k).eq.0) then
      do l=1,6
        nnmap2=map2(neigh(l,1),neigh(l,2),neigh(l,3))
        isexist=0
        do m=1,j_idx
          if (nnmap2.eq.j_lab(m)) then
            isexist=1
            exit
          endif
        enddo
        if (isexist.eq.0.and.nnmap2.ne.0) then
          j_idx=j_idx+1
          j_lab(j_idx)=nnmap2
        endif
      enddo

      if (j_idx.eq.2) then
        call push_fstack(j_lab(1),j_lab(2))
      endif
    endif

  enddo
  enddo
  enddo

  do k=1,nz
  do j=1,ny
  do i=1,nx
    call prepare_neigh(i,j,k,neigh)
    j_idx=0
    j_lab=0
    if (map(i,j,k).eq.0.and.ppt(i,j,k).eq.0) then
      do l=1,18
        nnmap2=map2(neigh(l,1),neigh(l,2),neigh(l,3))
        isexist=0
        do m=1,j_idx
          if (nnmap2.eq.j_lab(m)) then
            isexist=1
            exit
          endif
        enddo
        if (isexist.eq.0.and.nnmap2.ne.0) then
          j_idx=j_idx+1
          j_lab(j_idx)=nnmap2
        endif
      enddo

      if (j_idx.eq.3) then
        call push_tristack(j_lab(1),j_lab(2),j_lab(3))
      else if (j_idx.eq.4) then
        call push_quadstack(j_lab(1),j_lab(2),j_lab(3),j_lab(4),i,j,k, s_eta)
      endif
    endif

  enddo
  enddo
  enddo

  ave_f=2.0*float(nf)/ng
  ave_gb_area=float(sum(fidx))/(2.0*nf)
  ave_tri=3.0*float(ntri)/ng
  ave_quad=4.0*float(nquad)/ng

end

!push fstack
! m1
! m2
! fstack
! fidx
! nf 
subroutine push_fstack(m1,m2)
  ! use global
  use quantification_3d, push_fstack_from_self => push_fstack

  implicit none
  integer,intent(in) :: m1,m2
  integer :: g1,g2
  integer :: tmp(2),i,idx

  tmp(1)=m1
  tmp(2)=m2

  g1=maxval(tmp)
  g2=minval(tmp)

  idx=0
  do i=1,nf
    if (g1.eq.fstack(i,1)) then
      if (g2.eq.fstack(i,2)) then
        idx=i
        exit
      endif
    endif
  enddo

  if (idx.eq.0) then
    nf=nf+1
    fstack(nf,1)=g1
    fstack(nf,2)=g2
    fidx(nf)=1
  else
    fidx(idx)=fidx(idx)+1
  endif

end


!push tristack
subroutine push_tristack(m1,m2,m3)
  ! use global
  use quantification_3d, push_tristack_from_self => push_tristack

  implicit none
  integer,intent(in) :: m1,m2,m3
  integer :: g1,g2,g3
  integer :: tmp(3),i,idx

  tmp(1)=m1
  tmp(2)=m2
  tmp(3)=m3

  g1=maxval(tmp)
  g3=minval(tmp)
  g2=sum(tmp)-g1-g3

  idx=0
  do i=1,ntri
    if (g1.eq.tristack(i,1)) then
      if (g2.eq.tristack(i,2)) then
        if (g3.eq.tristack(i,3)) then
          idx=i
          exit
        endif
      endif
    endif
  enddo

  if (idx.eq.0) then
    ntri=ntri+1
    tristack(ntri,1)=g1
    tristack(ntri,2)=g2
    tristack(ntri,3)=g3
  endif

end

!Push Quadstack
subroutine push_quadstack(g1,g2,g3,g4,x,y,z,s_eta)
  ! use global
  use quantification_3d, push_quadstack_from_self => push_quadstack

  implicit none
  integer,intent(inout) :: g1,g2,g3,g4
  integer,intent(in)::x,y,z
  real,intent(in),dimension(:,:,:) :: s_eta
  integer :: tmp(4),i,j,l,idx
  integer :: q(4),sameCnt

  tmp(1)=g1
  tmp(2)=g2
  tmp(3)=g3
  tmp(4)=g4

  do i=1,4
  do j=i,4
    if (tmp(i).lt.tmp(j)) then
      idx=tmp(i)
      tmp(i)=tmp(j)
      tmp(j)=idx
    endif
  enddo
  enddo

  g1=tmp(1)
  g2=tmp(2)
  g3=tmp(3)
  g4=tmp(4)

  idx=0
  do i=1,nquad
    if (g1.eq.quadstack(i,1)) then
      if (g2.eq.quadstack(i,2)) then
        if (g3.eq.quadstack(i,3)) then
          if (g4.eq.quadstack(i,4)) then
            idx=i
            exit
          endif
        endif
      endif
    endif
  enddo

  if (idx.eq.0) then
    nquad=nquad+1
    quadstack(nquad,1)=g1
    quadstack(nquad,2)=g2
    quadstack(nquad,3)=g3
    quadstack(nquad,4)=g4
    quadpos(nquad,1)=x
    quadpos(nquad,2)=y
    quadpos(nquad,3)=z
  else
    if (s_eta(quadpos(idx,1),quadpos(idx,2),quadpos(idx,3)).gt.s_eta(x,y,z)) then
      quadpos(idx,1)=x
      quadpos(idx,2)=y
      quadpos(idx,3)=z
    endif
  endif

end

subroutine push_removestack(idx)
  ! use global
  use quantification_3d, push_removestack_from_self => push_removestack

  implicit none
  integer,intent(in) :: idx

  ridx=ridx+1
  removestack(ridx)=idx

end

subroutine remove_tristack_element
  ! use global
  use quantification_3d !, remove_tristack_from_self => remove_tristack_element

  implicit none
  integer :: rtri_idx


  call pop_removestack(rtri_idx)

  tristack(rtri_idx:ntri-1,:)=tristack(rtri_idx+1:ntri,:)
  ntri=ntri-1

end

subroutine pop_removestack(rtri_idx)
  ! use global
  use quantification_3d, pop_removestack_from_self => pop_removestack

  implicit none
  integer,intent(out) :: rtri_idx 

  rtri_idx=removestack(ridx)
  ridx=ridx-1

end

subroutine initiate_Tristack
  ! use global
  use quantification_3d

  implicit none

  ntri=0
  tristack=0

end

subroutine initiate_Quadstack
  ! use global
  use quantification_3d

  implicit none
  nquad=0
  quadstack=0

end

subroutine Initiate_Fstack
  ! use global
  use quantification_3d

  implicit none

  nf=0
  fstack=0
  fidx=0

end

subroutine prepare_neigh(i,j,k, neigh)
  ! use global
  use quantification_3d, prepare_neigh_from_self => prepare_neigh

  implicit none
  integer,intent(in) :: i,j,k
  integer, intent(out),dimension(26,3) :: neigh
  integer :: cxn,cxp,cyn,cyp,czn,czp

  cxn=xn(i)
  cxp=xp(i)
  cyn=yn(j)
  cyp=yp(j)
  czn=zn(k)
  czp=zp(k)

  neigh(1,1)=cxn
  neigh(1,2)=j
  neigh(1,3)=k
  neigh(2,1)=cxp
  neigh(2,2)=j
  neigh(2,3)=k
  neigh(3,1)=i
  neigh(3,2)=cyn
  neigh(3,3)=k
  neigh(4,1)=i
  neigh(4,2)=cyp
  neigh(4,3)=k
  neigh(5,1)=i
  neigh(5,2)=j
  neigh(5,3)=czn
  neigh(6,1)=i
  neigh(6,2)=j
  neigh(6,3)=czp

  neigh(7,1)=cxn
  neigh(7,2)=cyn
  neigh(7,3)=k
  neigh(8,1)=cxp
  neigh(8,2)=cyn
  neigh(8,3)=k
  neigh(9,1)=cxn
  neigh(9,2)=cyp
  neigh(9,3)=k
  neigh(10,1)=cxp
  neigh(10,2)=cyp
  neigh(10,3)=k

  neigh(11,1)=cxn
  neigh(11,2)=j
  neigh(11,3)=czn
  neigh(12,1)=cxp
  neigh(12,2)=j
  neigh(12,3)=czn
  neigh(13,1)=cxn
  neigh(13,2)=j
  neigh(13,3)=czp
  neigh(14,1)=cxp
  neigh(14,2)=j
  neigh(14,3)=czp

  neigh(15,1)=i
  neigh(15,2)=cyn
  neigh(15,3)=czn
  neigh(16,1)=i
  neigh(16,2)=cyp
  neigh(16,3)=czn
  neigh(17,1)=i
  neigh(17,2)=cyn
  neigh(17,3)=czp
  neigh(18,1)=i
  neigh(18,2)=cyp
  neigh(18,3)=czp

  neigh(19,1)=cxn
  neigh(19,2)=cyn
  neigh(19,3)=czn
  neigh(20,1)=cxp
  neigh(20,2)=cyn
  neigh(20,3)=czn
  neigh(21,1)=cxn
  neigh(21,2)=cyp
  neigh(21,3)=czn
  neigh(22,1)=cxn
  neigh(22,2)=cyn
  neigh(22,3)=czp
  neigh(23,1)=cxp
  neigh(23,2)=cyp
  neigh(23,3)=czn
  neigh(24,1)=cxp
  neigh(24,2)=cyn
  neigh(24,3)=czp
  neigh(25,1)=cxn
  neigh(25,2)=cyp
  neigh(25,3)=czp

  neigh(26,1)=cxp
  neigh(26,2)=cyp
  neigh(26,3)=czp

end
