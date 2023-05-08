!Program to quantify the face
!Code written at June 11th 2020
!Code written by Kunok Chang and Hyeonho Kim (kunok.chang@khu.ac.kr, hyeonhokim1823@khu.ac.kr)

subroutine hetero2D
  use global
  implicit none
  integer :: i,j,l,m
  integer :: j_lab(8),j_idx,nnmap2,isexist

  ridx=0

  do j=1,ny
  do i=1,nx
    call prepare_neigh(i,j)
    j_idx=0
    j_lab=0
    if (map(i,j).eq.0) then
      do l=1,4
        nnmap2=map2(neigh(l,1),neigh(l,2))
        isexist=0
        do m=1,j_idx
          if (nnmap2.eq.j_lab(m)) then
            isexist=1
            exit
          endif
        enddo
        if (isexist.eq.0) then
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

  do j=1,ny
  do i=1,nx
    call prepare_neigh(i,j)
    
    j_idx=0
    j_lab=0
    if (map(i,j).eq.0) then
      do l=1,8
        nnmap2=map2(neigh(l,1),neigh(l,2))
        isexist=0
        do m=1,j_idx
          if (nnmap2.eq.j_lab(m)) then
            isexist=1
            exit
          endif
        enddo
        if (isexist.eq.0) then
          j_idx=j_idx+1
          j_lab(j_idx)=nnmap2
        endif
      enddo
      if (j_idx.eq.3) then
        call push_tristack(j_lab(1),j_lab(2),j_lab(3),i,j)
      endif
    endif
  enddo
  enddo
  do j=1,ny
  do i=1,nx
    call prepare_neigh(i,j)
    j_idx=0
    j_lab=0
    if (map(i,j).eq.0) then
      do l=1,8
        nnmap2=map2(neigh(l,1),neigh(l,2))
        isexist=0
        do m=1,j_idx
          if (nnmap2.eq.j_lab(m)) then
            isexist=1
            exit
          endif
        enddo
        if (isexist.eq.0) then
          j_idx=j_idx+1
          j_lab(j_idx)=nnmap2
        endif
      enddo
      if (j_idx.eq.4) then
        call push_quadstack(j_lab(1),j_lab(2),j_lab(3),j_lab(4),i,j)
      endif
    endif
  enddo
  enddo
  ave_f=2.0*float(nf)/ng
  ave_gb_length=float(sum(fidx))/(2.0*nf)
  ave_tri=3.0*float(ntri)/ng
  ave_quad=4.0*float(nquad)/ng
  if(istep.eq.10000.or.istep.eq.20000.or.istep.eq.nstep.or.istep.eq.30000.or.istep.eq.40000) then
     call establish_group 
     call calculate_angle
  endif
end
!To set triple-junction group
subroutine establish_group
  use global
  implicit none
  integer :: i,j,l,m,a,b,k,e,h,o,q,c,d,z,u,pp,t
  real :: max_th,mid_th,min_th,angle_tot
  integer:: dummy_n,dummy_b
  real:: dummy_a
  integer,parameter :: p=1
  integer :: len
  integer :: count1,count2,count3,count_tq
  character(len=1000) :: foldername
  character(len=1000) :: ffilename
  character(len=100) :: temp_arraydata
  character(len=100) :: except_quadra
  character(len=100) :: temp_point
  character(len=100) :: angle_gb
  character(len=100) :: group_ddata
  character(len=100) :: step
  character(len=100) :: member_num
  character(len=100) :: gr
  character(len=100) :: tri_pos
  ntri_except=0
  except_idx=0
  call calculate_angle

  !sorting and classified grain
  do m=1,ntri
    do i=1,sx
    do j=1,sy
      call prepare_neigh(i,j)
      a=tripos(m,1)-3+i
      b=tripos(m,2)-3+j
      if(a.le.0) then
        a=nx+a
      else if(a.gt.nx) then
        a=a-nx
      endif
      if(b.le.0) then
        b=ny+b
      else if(b.gt.ny) then
        b=b-ny
      endif
      geta=0
      geta_m=0
      do l=1,nop(a,b)
        if(eta(l,a,b).gt.geta(a,b)) then
          geta_m(a,b)=geta(a,b)
          geta(a,b)=eta(l,a,b)
          gn(a,b)=gid(l,a,b)
        else if(eta(l,a,b).gt.geta_m(a,b)) then
          geta_m(a,b)=eta(l,a,b)
          gn_m(a,b)=gid(l,a,b)
        endif 
       enddo 
       if(i.eq.1.and.j.eq.1) then
         lgn(m,1)=gn(a,b)
       else if(i.eq.sx.and.j.eq.sy) then
         lgn(m,2)=gn(a,b)
         if(lgn(m,1).eq.lgn(m,2)) then
           lgn(m,1)=gn_m(a,b)
         endif
       endif
    enddo
    enddo
  enddo
  do m=1,ntri
    q=0
    do i=1,sx
    do j=1,sy
      a=tripos(m,1)-3+i
      b=tripos(m,2)-3+j 
      if(a.le.0) then
        a=nx+a
      else if(a.gt.nx) then
        a=a-nx
      endif
      if(b.le.0) then
        b=ny+b
      else if(b.gt.ny) then
        b=b-ny
      endif
      if(gn(a,b).ne.lgn(m,1).and.gn(a,b).ne.lgn(m,2)) then
        lgn(m,3)=gn(a,b)
      endif
    enddo
    enddo

    !Check the number of quadratic-junction
    do i=1,sx
    do j=1,sy
      a=tripos(m,1)-3+i
      b=tripos(m,2)-3+j
      if(a.le.0) then
        a=nx+a
      else if(a.gt.nx) then
        a=a-nx
      endif
      if(b.le.0) then
        b=ny+b
      else if(b.gt.ny) then
        b=b-ny
      endif
      if(gn(a,b).ne.lgn(m,1).and.gn(a,b).ne.lgn(m,2).and.gn(a,b).ne.lgn(m,3)) then
        q=1
      endif
    enddo
    enddo  
    if(q.eq.1) then
      except_idx=except_idx+1
      ntri_except(except_idx)=m
    endif
  enddo
  write(*,*) ntri
  write(step,*) istep
  if(istep.eq.10000.or.istep.eq.20000.or.istep.eq.30000.or.istep.eq.40000.or.istep.eq.50000) then
    write(except_quadra,*) "except_quarda"
    open(unit=120,file=except_quadra(:13)//step)
  endif              
  do m=1,except_idx
    write(120,*) m,ntri_except(m)
    !if (ntri_except(m)<ntri) then
      tristack(ntri_except(m)+(1-m):ntri-1,:)=tristack(ntri_except(m)+1+(1-m):ntri,:)
      tripos(ntri_except(m)+(1-m):ntri-1,:)=tripos(ntri_except(m)+1+(1-m):ntri,:)
      lgn(ntri_except(m)+(1-m):ntri-1,:)=lgn(ntri_except(m)+1+(1-m):ntri,:)
    !endif
    ntri=ntri-1
  enddo

  do m=1,ntri
    temp_array_area=0
    temp_array_point=0
    max_th=0.0
    mid_th=0.0
    min_th=0.0
    angle_tot=0.0
    count1=0
    count2=0
    count3=0
    write(tri_pos,*) "tri_pos"
    open(unit=139,file=tri_pos(:7)//step)
    write(139,*) m,tripos(m,1),tripos(m,2)    
    do i=1,sx
    do j=1,sy
      a=tripos(m,1)-3+i
      b=tripos(m,2)-3+j
      if(a.le.0) then
        a=nx+a
      else if(a.gt.nx) then
        a=a-nx
      endif
      if(b.le.0) then
        b=ny+b
      else if(b.gt.ny) then
        b=b-ny
      endif

      !Count number of the voxel each grain at each triple-junction
      if(gn(a,b).eq.lgn(m,1)) then
        temp_array_area(i,j)=1       
        count1=count1+1
      else if(gn(a,b).eq.lgn(m,2)) then
        temp_array_area(i,j)=2        
        count2=count2+1
      else if(gn(a,b).eq.lgn(m,3)) then
        temp_array_area(i,j)=3       
        count3=count3+1
      endif
     temp_array_a(m,i,j)=temp_array_area(i,j) 
     write(temp_arraydata,*) "temp_arraydata"
     open(unit=125,file=temp_arraydata(:14)//step)
     write(125,*) m,i,j,temp_array_area(i,j)
    count_l(m,1)=count1
    count_l(m,2)=count2
    count_l(m,3)=count3  
    enddo
    enddo  
    do i=1,sx
    do j=1,sy
      a=tripos(m,1)-3+i
      b=tripos(m,2)-3+j
      if(a.le.0) then
        a=nx+a
      else if(a.gt.nx) then
        a=a-nx
      endif
      if(b.le.0) then
        b=ny+b
      else if(b.gt.ny) then
        b=b-ny
      endif
      if((i.eq.1.or.i.eq.sx).or.(j.eq.1.or.j.eq.sy)) then       
        if((temp_array_area(i,j)).eq.1.and.(temp_array_area(i+2,j).eq.2.or.temp_array_area(i,j+2).eq.2)) then
          temp_array_point(1,1)=i
          temp_array_point(1,2)=j
        else if((temp_array_area(i,j)).eq.2.and.(temp_array_area(i-1,j).eq.3.or.temp_array_area(i,j-1).eq.3)) then
          temp_array_point(2,1)=i
          temp_array_point(2,2)=j
        else if((temp_array_area(i,j)).eq.3.and.(temp_array_area(i-1,j).eq.1.or.temp_array_area(i,j-1).eq.1)) then
          temp_array_point(3,1)=i
          temp_array_point(3,2)=j
        endif
      endif
    enddo
    enddo
    write(temp_point,*) "temp_point"
    open(unit=122,file=temp_point(:10)//step)
    write(122,*) m,temp_array_point(1,1),temp_array_point(1,2),temp_array_point(2,1),temp_array_point(2,2),temp_array_point(3,1),temp_array_point(3,2)
 
  !Calculate sharp-interface angle 
   do k=1,3
      do l=1,2
        vector(k,m,l)=temp_array_point(k,l)-3
      enddo
    enddo
    do l=1,3
      inner_gb(l,m)=vector(l,m,1)*vector(l+1,m,1)+vector(l,m,2)*vector(l+1,m,2)
      size_gb(l,m)=((vector(l,m,1)**2+vector(l,m,2)**2)**0.5)*((vector(l+1,m,1)**2+vector(l+1,m,2)**2)**0.5)
      if(l.eq.3) then
        inner_gb(l,m)=vector(l,m,1)*vector(l-2,m,1)+vector(l,m,2)*vector(l-2,m,2)
        size_gb(l,m)=((vector(l,m,1)**2+vector(l,m,2)**2)**0.5)*((vector(l-2,m,1)**2+vector(l-2,m,2)**2)**0.5)
      endif
      theta_gb(m,l)=acos(inner_gb(l,m)/size_gb(l,m))*(180.0/pi_math)
    enddo
    if((theta_gb(m,1)+theta_gb(m,2)+theta_gb(m,3)).le.359.9) then
      do l=1,3
        if(theta_gb(m,l).gt.max_th) then
          mid_th=max_th
          max_th=theta_gb(m,l)
        else if(theta_gb(m,l).gt.mid_th) then
          mid_th=theta_gb(m,l)
        endif
      enddo
      angle_tot=theta_gb(m,1)+theta_gb(m,2)+theta_gb(m,3)
      min_th=angle_tot-max_th-mid_th
      
      do l=1,3
        if(theta_gb(m,l).eq.mid_th) then
          theta_gb(m,l)=180.0-mid_th
        else if(theta_gb(m,l).ne.max_th.and.theta_gb(m,l).ne.mid_th) then
          theta_gb(m,l)=180.0-min_th
        endif
      enddo
    endif
    write(angle_gb,*) "angle_gb"
    open(unit=116,file=angle_gb(:8)//step)

     do dummy_b=1,2
     do u=1,3
        do pp=1,3
          if(count_l(m,u).gt.count_l(m,pp)) then
            dummy_n=count_l(m,u)
            count_l(m,u)=count_l(m,pp)
            count_l(m,pp)=dummy_n
            dummy_a=theta_gb(m,u)
            theta_gb(m,u)=theta_gb(m,pp)
            theta_gb(m,pp)=dummy_a
           elseif(count_l(m,u).eq.count_l(m,pp)) then
            if(theta_gb(m,u).gt.theta_gb(m,pp)) then
              dummy_a = theta_gb(m,u)
              theta_gb(m,u) = theta_gb(m,pp)
              theta_gb(m,pp) = dummy_a
            endif
          endif
        enddo
      enddo
    enddo

    do l=1,3
      write(116,*)m,theta_gb(m,l)   
    enddo
  enddo 
    if(istep.eq.10000) then
      ngr=1
    endif
  dummy=0
  group=0
  write(group_ddata,*) "group_data"
  open(unit=102,file=group_ddata(:11)//step)
  if(istep.eq.10000) then
  count_g=0
  group_data=0
  group_data_theta=0.0
 
 !Classify triple-junction to class 
  !ngr=number of group number     
  do m=1,ntri
    n=1
    do k=1,ntri
       d=0
           if(count_l(m,1).eq.count_l(k,1)) then
              if(count_l(m,2).eq.count_l(k,2)) then   
                 if(count_l(m,3).eq.count_l(k,3)) then  
                    if(theta_gb(m,1).eq.theta_gb(k,1)) then  
                      if(theta_gb(m,2).eq.theta_gb(k,2)) then
                        if(theta_gb(m,3).eq.theta_gb(k,3)) then                 
                          do e=1,ntri
                          do o=1,dummy(e)
                             if(group(e,o).eq.k) then
                               d=1
                             endif
                          enddo
                          enddo
                          if(d.eq.0) then
                            group(ngr,n)=k
                            !write(*,*) ngr,n,group(ngr,n)
                            group4(ngr)=n
                            if(n.eq.1) then
                              do l=1,3
                                group2(ngr,l)= theta_gb(m,l)
                                group3(ngr,l)= count_l(m,l)
                              enddo
                            endif                            
                            n=n+1
                          endif                 
                       endif
                     endif
                   endif
                 endif
               endif
             endif
            enddo
     if(n.ne.1) then
      dummy(ngr)=n
      ngr=ngr+1
    endif
    close(116)
    close(120)
    close(121)
    close(122)
  enddo
  do l=1,ngr    
    do i=1,3
      group_data(l,i)=group3(l,i)
      group_data_theta(l,i)=group2(l,i)
    enddo  
    count_g(l,1)=group4(l) 
    !write(*,*) "g",count_g(l,1)

    do i=1,group4(l)
      group_gl(l,1,i)=group(l,i)
      !write(*,*) group_gl(l,1,i)
    enddo
  enddo
  else
   dummy = 0 
    do m=1,ngr
      t=istep/10000
       do k=1,ntri
       d=0
       if(dummy(k).eq.0) then
           if(group_data(m,1).eq.count_l(k,1)) then
              if(group_data(m,2).eq.count_l(k,2)) then
                 if(group_data(m,3).eq.count_l(k,3)) then
                    if(group_data_theta(m,1).eq.theta_gb(k,1)) then
                      if(group_data_theta(m,2).eq.theta_gb(k,2)) then
                        if(group_data_theta(m,3).eq.theta_gb(k,3)) then
                          d=1      
                        endif
                     endif
                   endif
                 endif
               endif
             endif
             if(d.eq.1) then
               count_g(m,t)=count_g(m,t)+1
               group_gl(m,t,count_g(m,t))=k
               dummy(k) = 1
             endif                   
          endif
      enddo
    enddo
    
      do k=1,ntri
        if(dummy(k).eq.0) then
          dummy(k)=1
          ngr = ngr+1
          count_g(ngr,t)=count_g(ngr,t)+1
          group_gl(ngr,t,count_g(ngr,t))=k
          do i=1,3
            group_data(ngr,i)=count_l(k,i)
            group_data_theta(ngr,i)=theta_gb(k,i)
          enddo
          do m=1,ntri
          d=0
            if(dummy(k).eq.0) then
               if(group_data(ngr,1).eq.count_l(k,1)) then
              if(group_data(ngr,2).eq.count_l(k,2)) then
                 if(group_data(ngr,3).eq.count_l(k,3)) then
                    if(group_data_theta(ngr,1).eq.theta_gb(k,1)) then
                      if(group_data_theta(ngr,2).eq.theta_gb(k,2)) then
                        if(group_data_theta(ngr,3).eq.theta_gb(k,3)) then
                          d=1
                        endif
                     endif
                   endif
                 endif
               endif
             endif
             if(d.eq.1) then
               count_g(ngr,t)=count_g(ngr,t)+1
               group_gl(ngr,t,count_g(ngr,t))=k
               dummy(k) = 1
             endif
           endif  
            
          enddo
        endif
      enddo
    
  endif

  !Calculate angle distribution at each group
  do l=1,ngr
    theta_dist=0
    theta_dist_t=0
    t=istep/10000
    if(count_g(l,t).eq.0) then
      write(102,*) l,0,0
    else  
    do i=1,count_g(l,t)
      write(102,*) l,i,group_gl(l,t,i)
    enddo
    endif
    
    do i=1,count_g(l,t)
      do j=1,3
        do k=1,180/interval
          if((theta(group_gl(l,t,i),j)-(k*10.0)).ge.(-interval/2).and.(theta(group_gl(l,t,i),j)-(k*10.0)).lt.(interval/2)) then
             theta_dist(k)=theta_dist(k)+1
         endif
        enddo
      enddo
    enddo  
     write(ffilename,*) l
     open(unit=119,file=ffilename(:5)//step//'.txt')
     if(count_g(l,t).eq.1) then
       theta_dist_t=(count_g(l,t))*3
       do k=1,180/interval
         theta_distri(k)=theta_dist(k)/theta_dist_t
          write(119,*)l,k*10,theta_distri(k)
          if(k.eq.180/interval) then
            write(119,*) " "
          endif
       enddo
     else if(count_g(l,t).ne.1.and.count_g(l,t).ne.o) then
      theta_dist_t=(count_g(l,t)-1)*3
        do k=1,180/interval
          theta_distri(k)=theta_dist(k)/theta_dist_t
          write(119,*)l,k*10,theta_distri(k)
           if(k.eq.180/interval) then
            write(119,*) " "
          endif
       enddo
     else
       theta_dist_t=0
       do k=1,180/interval
          theta_distri(k)=theta_dist(k)/theta_dist_t
          write(119,*)l,k*10,theta_distri(k)
           if(k.eq.180/interval) then
            write(119,*) " "
          endif
       enddo              
     endif
  enddo
  close(140)
  close(141)
end

!To calculate gradient angle
subroutine calculate_angle
  use global
  implicit none
  integer :: i,j,k,l,m
  integer :: x,y,z
  real :: grad(3,2),a(2),b(2),dot,na,nb,temp,t1,t2,t3,tmp(3),tg(3),t(3)
  character(len=10):: filename
  character(len=100):: angle_inf
  character(len=100):: distribution
  character(len=100):: step
  character(len=100) :: dist_num
  theta_dist=0
  theta_dist_t=0
  do m=1,ntri
    i=tripos(m,1)
    j=tripos(m,2)
    call prepare_neigh(i,j)
    do l=1,nop(i,j)
      leta(gid(l,i,j),1)=eta(l,i,j)
    enddo
    !To use highest order,set up neigh2(1,1)-neigh2(8,2)
    do k=2,5
      do l=1,nop(neigh(k-1,1),neigh(k-1,2))
        leta(gid(l,neigh(k-1,1),neigh(k-1,2)),k)=eta(l,neigh(k-1,1),neigh(k-1,2))
      enddo
    enddo

    !To make 3D, you have to change j=1,3
    !Highest order derivative
    do i=1,3
      do j=1,2
        grad(i,j)=(leta(tristack(m,i),2*j)-leta(tristack(m,i),(2*j)+1))/(2.0*dx)     
      enddo
    enddo
     ! X,Y component of gradient
    do i=1,3
      if (i.eq.1) then
        a(:)=grad(1,:)
        b(:)=grad(2,:)
      else if (i.eq.2) then
        a(:)=grad(2,:)      
        b(:)=grad(3,:)
      else if (i.eq.3) then
        a(:)=grad(3,:)
        b(:)=grad(1,:)
      endif
       ! Gradient size
      na=sqrt((a(1)**2)+(a(2)**2))
      nb=sqrt((b(1)**2)+(b(2)**2))
      !inner product
      dot=a(1)*b(1)+a(2)*b(2)
      temp=acos(dot/(na*nb))
      if (temp.lt.pi_math/2.0.and.a(1)*b(1).lt.0.0.and.a(2)*b(2).lt.0.0) then
        temp=pi_math-temp
      endif
      theta(m,i)=temp*(180.0/pi_math)
      !Calculate angle distribution
      do k=1,180/interval
        if((theta(m,i)-(k*10.0)).ge.(-interval/2).and.(theta(m,i)-(k*10.0)).lt.(interval/2)) then
          theta_dist(k)=theta_dist(k)+1
        endif
      enddo 
      write(step,*) istep
      write(angle_inf,*) "angle_inf"
      open(unit=101,file=angle_inf(:9)//step)
      tg(i)=theta(m,i)
      theta_dist_t=ntri*3
      write(101,*) theta(m,i)
    enddo
  enddo
  close(101)
  write(distribution,*) "distribution"
  open(unit=118,file=distribution(:12)//step)
  write(dist_num,*) 'dist_num'
  open(unit=128,file=dist_num(:10)//step)

  do k=1,180/interval
    theta_distri(k)=theta_dist(k)/theta_dist_t 
    write(118,*)k*10,theta_distri(k)
    write(128,*)k*10,theta_distri(k),1/((theta_dist(k))**0.5)
  enddo  
  close(118)
  close(128)
end


!Push Fstack
subroutine push_fstack(m1,m2)
  use global
  implicit none
  integer :: m1,m2
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


!Push Tristack
subroutine push_tristack(m1,m2,m3,x,y)
  use global
  implicit none
  integer :: m1,m2,m3,x,y
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
    tripos(ntri,1)=x
    tripos(ntri,2)=y
  else 
    if (s_eta(tripos(idx,1),tripos(idx,2)).gt.s_eta(x,y)) then
      tripos(idx,1)=x
      tripos(idx,2)=y
    endif
  endif

end

!Push Quadstack
subroutine push_quadstack(g1,g2,g3,g4,x,y)
  use global
  implicit none
  integer :: g1,g2,g3,g4,x,y
  integer :: tmp(4),i,j,l,idx
  integer :: q(4),t(3),sameCnt


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
    do l=1,ntri
      t=tristack(l,:)
      q=quadstack(nquad,:)
      sameCnt=0
      do i=1,3
      do j=1,4
        if (t(i).eq.q(j)) sameCnt=sameCnt+1
      enddo
      enddo
      if (sameCnt.eq.3) then
        call push_removestack(l)
      endif
    enddo

    do while (ridx.gt.0)
      call remove_tristack_element
    enddo

  else
    if (s_eta(quadpos(idx,1),quadpos(idx,2)).gt.s_eta(x,y)) then
      quadpos(idx,1)=x
      quadpos(idx,2)=y
    endif
  endif

end

subroutine push_removestack(idx)
  use global
  implicit none
  integer :: idx

  ridx=ridx+1
  removestack(ridx)=idx

end

subroutine remove_tristack_element
  use global
  implicit none
  integer :: rtri_idx
 
  call pop_removestack(rtri_idx)

  tristack(rtri_idx:ntri-1,:)=tristack(rtri_idx+1:ntri,:)
  tripos(rtri_idx:ntri-1,:)=tripos(rtri_idx+1:ntri,:)
  ntri=ntri-1

end

subroutine pop_removestack(rtri_idx)
  use global
  implicit none
  integer :: rtri_idx

  rtri_idx=removestack(ridx)
  ridx=ridx-1

end

subroutine initiate_Tristack
  use global
  implicit none

  ntri=0
  tristack=0

end

subroutine initiate_Quadstack
  use global
  implicit none

  nquad=0
  quadstack=0

end

subroutine Initiate_Fstack
  use global
  implicit none

  nf=0
  fstack=0
  fidx=0

end

subroutine prepare_neigh(i,j)
  use global
  implicit none
  integer :: i,j
  integer :: cxn,cxp,cyn,cyp

  cxn=xn(i)
  cxp=xp(i)
  cyn=yn(j)
  cyp=yp(j)

  neigh(1,1)=cxn
  neigh(1,2)=j
  neigh(2,1)=cxp
  neigh(2,2)=j
  neigh(3,1)=i
  neigh(3,2)=cyn
  neigh(4,1)=i
  neigh(4,2)=cyp
  neigh(5,1)=cxn
  neigh(5,2)=cyn
  neigh(6,1)=cxp
  neigh(6,2)=cyn
  neigh(7,1)=cxn
  neigh(7,2)=cyp
  neigh(8,1)=cxp
  neigh(8,2)=cyp

end
