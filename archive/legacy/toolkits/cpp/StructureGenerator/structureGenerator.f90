! For simplicity this program is a seiral one rather than mpi

module mod_Struct_Gen
    use,intrinsic:: ISO_Fortran_env
    use double_precision
    use free_format
    use print_utilities
    implicit none
!    integer,parameter::idp=int64
!    integer,parameter::rdp=real64
!    integer,parameter::cdp=8
    integer :: nx,ny,nz
    logical,allocatable,dimension(:,:,:) :: domainBool
    logical,allocatable,dimension(:,:,:) :: localDomainBool
    real(kind=rdp),allocatable,dimension(:,:,:) :: numberedDomain
    character(len=300),dimension(:,:),allocatable:: wholeList
    integer :: domainLabel,wholeLevel
    integer,dimension(3) :: bound
    real(kind=rdp) memory




    interface writeOutput
        procedure writeOutputScalar
        procedure writeOutputScalar_integer
        procedure writeOutput4D
        procedure writeOutputVector
        procedure writeOutputTensor
    end interface

    interface duplicateDomain
        module procedure duplicatePlaneDomain
        module procedure duplicateRoundDomain
        module procedure duplicateParallelpipedDomain
        module procedure duplicateTrapezoidDomain
    end interface

contains




    subroutine generateInputStructure(filename,data1,data2,data3)
        implicit none
        real(kind=rdp),dimension(:,:,:),intent(in) :: data1
        real(kind=rdp),dimension(:,:,:),optional,intent(in) :: data2,data3
        character(len=:),allocatable,intent(in) :: filename
        character(len=:),allocatable :: filenameFull
        filenameFull=filename//".in"
        if(present(data2).and.present(data3)) then
            call writeOutput(filenameFull,data1,data2,data3)
        else
            call writeOutput(filenameFull,data1)
        endif
    end subroutine


    subroutine writeOutput4D(filenameFull,data)
        implicit none
        character(len=:),allocatable,intent(in) :: filenameFull
        real(kind=rdp),dimension(:,:,:,:),intent(in) :: data
        integer i,j,k,l,nx,ny,nz,nsize,ierr,iounit
        character(len=35) headerFMT,bodyFMT,positionFMT
        character(len=100) stringHold

        nsize=size(data,dim=1)
        nx=size(data,dim=4)
        ny=size(data,dim=3)
        nz=size(data,dim=2)

        iounit=1
        headerFMT="(3(1x,i5),A16,A2)"
        positionFMT="3(1x,i5)"
        bodyFMT="(1x,es15.7e3)"
        ! write(bodyFMT,'(A,I,A)' "(3(1x,i5),",nsize,"(1x,es15.7e3),A2)"

        open(unit=iounit, file=trim(filenameFull), iostat=ierr)
        write(unit=iounit, fmt=headerFMT) nx,ny,nz," "
        do i=1,nx
            do j=1,ny
                do k=1,nz
                    write(unit=iounit, fmt=positionFMT) i,j,k

                    do l=1,nsize
                        write(unit=iounit, fmt=bodyFMT,advance='no') data(l,k,j,i)
                    enddo

                    write(unit=iounit, fmt='(A)') achar(32)
                enddo
            enddo
        enddo

        close(iounit)

    end subroutine


    subroutine writeOutputScalar(filenameFull,data1)
        implicit none
        character(len=:),allocatable,intent(in) :: filenameFull
        real(kind=rdp),dimension(:,:,:),intent(in) :: data1
        integer i,j,k,nx,ny,nz,ierr,iounit
        character(len=35) headerFMT,bodyFMT

        nx=size(data1,dim=3)
        ny=size(data1,dim=2)
        nz=size(data1,dim=1)

        iounit=1
        headerFMT="(3(1x,i5),A16,A2)"
        bodyFMT="(3(1x,i5),(1x,es15.7e3),A2)"

        open(unit=iounit, file=trim(filenameFull), iostat=ierr)
        write(unit=iounit, fmt=headerFMT) nx,ny,nz," "
        do i=1,nx
            do j=1,ny
                do k=1,nz
                    write(unit=iounit, fmt=bodyFMT) i,j,k,data1(k,j,i)
                enddo
            enddo
        enddo

        close(iounit)

    end subroutine

    subroutine writeOutputScalar_integer(filenameFull,data1)
        implicit none
        character(len=:),allocatable,intent(in) :: filenameFull
        integer,dimension(:,:,:),intent(in) :: data1
        integer i,j,k,nx,ny,nz,ierr,iounit
        character(len=35) headerFMT,bodyFMT

        nx=size(data1,dim=3)
        ny=size(data1,dim=2)
        nz=size(data1,dim=1)

        iounit=1
        headerFMT="(3(1x,i5),A16,A2)"
        bodyFMT="(3(1x,i5),(1x,I10),A2)"

        open(unit=iounit, file=trim(filenameFull), iostat=ierr)
        write(unit=iounit, fmt=headerFMT) nx,ny,nz," "
        do i=1,nx
            do j=1,ny
                do k=1,nz
                    write(unit=iounit, fmt=bodyFMT) i,j,k,data1(k,j,i)
                enddo
            enddo
        enddo

        close(iounit)

    end subroutine


    subroutine writeOutputVector(filenameFull,data1,data2,data3)
        implicit none
        character(len=:),allocatable,intent(in) :: filenameFull
        real(kind=rdp),dimension(:,:,:),intent(in) :: data1,data2,data3
        integer i,j,k,nx,ny,nz,ierr,iounit
        character(len=35) headerFMT,bodyFMT

        if(     .not. ( &
            ( (size(data1,dim=1).eq.size(data2,dim=1)) .and. (size(data2,dim=1).eq.size(data3,dim=1)) )  .and. &
            ( (size(data1,dim=2).eq.size(data2,dim=2)) .and. (size(data2,dim=2).eq.size(data3,dim=2)) )  .and. &
            ( (size(data1,dim=3).eq.size(data2,dim=3)) .and. (size(data2,dim=3).eq.size(data3,dim=3)) )  )) then
            print *,"The dimension for vector components are not the same"
            stop
        endif

        nx=size(data1,dim=3)
        ny=size(data1,dim=2)
        nz=size(data1,dim=1)

        iounit=1
        headerFMT="(3(1x,i5),A48,A2)"
        bodyFMT="(3(1x,i5),3(1x,es15.7e3),A2)"

        open(unit=iounit, file=trim(filenameFull), iostat=ierr)
        write(unit=iounit, fmt=headerFMT) nx,ny,nz," "
        do i=1,nx
            do j=1,ny
                do k=1,nz
                    write(unit=iounit, fmt=bodyFMT) i,j,k,data1(k,j,i),data2(k,j,i),data3(k,j,i)
                enddo
            enddo
        enddo

        close(iounit)

    end subroutine


    subroutine writeOutputTensor(filenameFull,data1,data2,data3,data4,data5,data6)
        implicit none
        character(len=:),allocatable,intent(in) :: filenameFull
        real(kind=rdp),dimension(:,:,:),intent(in) :: data1,data2,data3,data4,data5,data6
        integer i,j,k,nx,ny,nz,ierr,iounit
        character(len=35) headerFMT,bodyFMT

        if(     .not. ( &
            ( (size(data1,dim=1).eq.size(data2,dim=1)) .and. (size(data2,dim=1).eq.size(data3,dim=1)) )  .and. &
            ( (size(data1,dim=2).eq.size(data2,dim=2)) .and. (size(data2,dim=2).eq.size(data3,dim=2)) )  .and. &
            ( (size(data1,dim=3).eq.size(data2,dim=3)) .and. (size(data2,dim=3).eq.size(data3,dim=3)) )  )) then
            print *,"The dimension for tensor components are not the same"
            stop
        endif

        nx=size(data1,dim=3)
        ny=size(data1,dim=2)
        nz=size(data1,dim=1)

        iounit=1
        headerFMT="(3(1x,i5),A48,A2)"
        bodyFMT="(3(1x,i5),6(1x,es15.7e3),A2)"

        open(unit=iounit, file=trim(filenameFull), iostat=ierr)
        write(unit=iounit, fmt=headerFMT) nx,ny,nz," "
        do i=1,nx
            do j=1,ny
                do k=1,nz
                    write(unit=iounit, fmt=bodyFMT) i,j,k,data1(k,j,i),data2(k,j,i),data3(k,j,i),data4(k,j,i),data5(k,j,i),data6(k,j,i)
                enddo
            enddo
        enddo

        close(iounit)

    end subroutine

    subroutine duplicatePlaneDomain(domainBoolIn,point,normal,distance,bound,repeatDomain)
        use structure,only: defineCenterDomain,inBoundFunction6
        implicit none
        integer i,shiftHold
        real(kind=rdp),dimension(3),intent(in) :: repeatDomain,normal
        real(kind=rdp) :: repeatDomainLength
        real(kind=rdp) :: distance
        real(kind=rdp),dimension(3) :: hold
        real(kind=rdp),dimension(3),intent(inout) :: point
        integer,dimension(6),intent(in) :: bound
        integer,dimension(3) :: localbound
        logical,dimension(:,:,:),intent(inout) :: domainBoolIn
        logical,dimension(:,:,:),allocatable :: domainOrigin,domainHold
        allocate(domainOrigin(size(domainBoolIn,1),size(domainBoolIn,2),size(domainBoolIn,3)))
        allocate(domainHold(size(domainBoolIn,1),size(domainBoolIn,2),size(domainBoolIn,3)))

        domainOrigin = domainBoolIn
        domainHold = domainBoolIn
        repeatDomainLength = repeatDomain(1)**2+repeatDomain(2)**2+repeatDomain(3)**2

        ! do i = 1,3
            if(repeatDomainLength.gt.1) then
                hold=point
                do while(inBoundFunction6(point,bound))
                    point=point+repeatDomain
                    call defineCenterDomain(domainBoolIn,point,normal,distance,localbound)
                    call printVariable( "Duplicate plane along # at position",point(1),point(2),point(3))
                    ! domainHold = CSHIFT(domainOrigin,shift=floor(point(i)-hold),dim=i)
                    ! shiftHold=floor(point(i)-hold)
                    ! domainHold = CSHIFT(domainOrigin,shift=shiftHold,dim=i)
                    ! domainBool = domainHold
                    ! domainBool = domainBool.or.domainHold
                    ! exit
                    ! domainBool = CSHIFT(domainOrigin,floor(point(i)-hold),dim=i)
                    ! domainBool = CSHIFT(domainOrigin,shift=10,dim=1)
                enddo

                point=hold

                do while(inBoundFunction6(point,bound))
                    point=point-repeatDomain
                    call printVariable( "Duplicate plane along # at position",point(1),point(2),point(3))
                    call defineCenterDomain(domainBoolIn,point,normal,distance,bound)
                    ! shiftHold=floor(point(i)-hold)
                    ! domainHold = CSHIFT(domainOrigin,shift=shiftHold,dim=i)
                    ! domainBool = domainBool.or.domainHold
                    ! domainBool = CSHIFT(domainOrigin,floor(point(i)-hold),dim=i)
                enddo
            endif
        ! enddo
    endsubroutine



    subroutine duplicateRoundDomain(domainBoolIn,point,radius,direction,choice_surface,bound,repeatDomain)
        use structure,only: defineRoundPillarDomain,inBoundFunction6
        implicit none
        integer i,shiftHold
        real(kind=rdp),dimension(3),intent(in) :: repeatDomain,direction
        real(kind=rdp) :: hold,radius
        integer,intent(in) :: choice_surface
        real(kind=rdp),dimension(3),intent(inout) :: point
        integer,dimension(6),intent(in) :: bound
        logical,dimension(:,:,:),intent(inout) :: domainBoolIn
        logical,dimension(:,:,:),allocatable :: domainOrigin,domainHold
        allocate(domainOrigin(size(domainBoolIn,1),size(domainBoolIn,2),size(domainBoolIn,3)))
        allocate(domainHold(size(domainBoolIn,1),size(domainBoolIn,2),size(domainBoolIn,3)))

        domainOrigin = domainBoolIn
        domainHold = domainBoolIn

        do i = 1,3
            if(repeatDomain(i).gt.1) then
                hold=point(i)
                do while(inBoundFunction6(point,bound))
                    point(i)=point(i)+repeatDomain(i)
                    call printVariable( "Duplicate pillar along # at position",i,floor(point(i)))
                    call defineRoundPillarDomain(domainBoolIn,point,radius,direction,choice_surface,bound)
                    ! domainHold = CSHIFT(domainOrigin,shift=floor(point(i)-hold),dim=i)
                    ! shiftHold=floor(point(i)-hold)
                    ! domainHold = CSHIFT(domainOrigin,shift=shiftHold,dim=i)
                    ! domainBool = domainHold
                    ! domainBool = domainBool.or.domainHold
                    ! exit
                    ! domainBool = CSHIFT(domainOrigin,floor(point(i)-hold),dim=i)
                    ! domainBool = CSHIFT(domainOrigin,shift=10,dim=1)
                enddo

                point(i)=hold

                do while(inBoundFunction6(point,bound))
                    point(i)=point(i)-repeatDomain(i)
                    call printVariable( "Duplicate pillar along # at position",i,floor(point(i)))
                    call defineRoundPillarDomain(domainBoolIn,point,radius,direction,choice_surface,bound)
                    ! shiftHold=floor(point(i)-hold)
                    ! domainHold = CSHIFT(domainOrigin,shift=shiftHold,dim=i)
                    ! domainBool = domainBool.or.domainHold
                    ! domainBool = CSHIFT(domainOrigin,floor(point(i)-hold),dim=i)
                enddo
            endif
        enddo
    endsubroutine



    subroutine duplicateParallelpipedDomain(domainBoolIn,point,pointA,pointB,direction,choice_surface,bound,repeatDomain)
        use structure,only: defineParallelpipedPillarDomain,inBoundFunction6
        implicit none
        integer i,shiftHold
        real(kind=rdp),dimension(3),intent(in) :: repeatDomain,direction
        real(kind=rdp) :: hold,holdA,holdB
        integer,intent(in) :: choice_surface
        real(kind=rdp),dimension(3),intent(inout) :: point,pointA,pointB
        integer,dimension(6),intent(in) :: bound
        logical,dimension(:,:,:),intent(inout) :: domainBoolIn
        logical,dimension(:,:,:),allocatable :: domainOrigin,domainHold
        allocate(domainOrigin(size(domainBoolIn,1),size(domainBoolIn,2),size(domainBoolIn,3)))
        allocate(domainHold(size(domainBoolIn,1),size(domainBoolIn,2),size(domainBoolIn,3)))

        domainOrigin = domainBoolIn
        domainHold = domainBoolIn

        do i = 1,3
            if(repeatDomain(i).gt.1) then
                hold=point(i)
                holdA=pointA(i)
                holdB=pointB(i)
                do while(inBoundFunction6(point,bound))
                    point(i)=point(i)+repeatDomain(i)
                    pointA(i)=pointA(i)+repeatDomain(i)
                    pointB(i)=pointB(i)+repeatDomain(i)
                    call printVariable( "Duplicate pillar along # at position",i,floor(point(i)))
                    call defineParallelpipedPillarDomain(domainBoolIn,point,pointA,pointB,direction,choice_surface,bound)
                    ! domainHold = CSHIFT(domainOrigin,shift=floor(point(i)-hold),dim=i)
                    ! shiftHold=floor(point(i)-hold)
                    ! domainHold = CSHIFT(domainOrigin,shift=shiftHold,dim=i)
                    ! domainBool = domainHold
                    ! domainBool = domainBool.or.domainHold
                    ! exit
                    ! domainBool = CSHIFT(domainOrigin,floor(point(i)-hold),dim=i)
                    ! domainBool = CSHIFT(domainOrigin,shift=10,dim=1)
                enddo

                point(i)=hold
                pointA(i)=holdA
                pointB(i)=holdB

                do while(inBoundFunction6(point,bound))
                    point(i)=point(i)-repeatDomain(i)
                    pointA(i)=pointA(i)-repeatDomain(i)
                    pointB(i)=pointB(i)-repeatDomain(i)
                    call printVariable( "Duplicate pillar along # at position",i,floor(point(i)))
                    call defineParallelpipedPillarDomain(domainBoolIn,point,pointA,pointB,direction,choice_surface,bound)
                    ! shiftHold=floor(point(i)-hold)
                    ! domainHold = CSHIFT(domainOrigin,shift=shiftHold,dim=i)
                    ! domainBool = domainBool.or.domainHold
                    ! domainBool = CSHIFT(domainOrigin,floor(point(i)-hold),dim=i)
                enddo
            endif
        enddo
    endsubroutine


    subroutine duplicateTrapezoidDomain(domainBoolIn,point,pointA,pointB,pointC,pointD,direction,choice_surface,bound,repeatDomain)
        use structure,only: defineTrapezoidPillarDomain,inBoundFunction6
        implicit none
        integer i,shiftHold
        real(kind=rdp),dimension(3),intent(in) :: repeatDomain,direction
        real(kind=rdp) :: hold,holdA,holdB,holdC,holdD
        integer,intent(in) :: choice_surface
        real(kind=rdp),dimension(3),intent(inout) :: point,pointA,pointB,pointC,pointD
        integer,dimension(6),intent(in) :: bound
        logical,dimension(:,:,:),intent(inout) :: domainBoolIn
        logical,dimension(:,:,:),allocatable :: domainOrigin,domainHold
        allocate(domainOrigin(size(domainBoolIn,1),size(domainBoolIn,2),size(domainBoolIn,3)))
        allocate(domainHold(size(domainBoolIn,1),size(domainBoolIn,2),size(domainBoolIn,3)))

        domainOrigin = domainBoolIn
        domainHold = domainBoolIn

        do i = 1,3
            if(repeatDomain(i).gt.1) then
                hold=point(i)
                holdA=pointA(i)
                holdB=pointB(i)
                holdC=pointC(i)
                holdD=pointD(i)
                do while(inBoundFunction6(point,bound))
                    point(i)=point(i)+repeatDomain(i)
                    pointA(i)=pointA(i)+repeatDomain(i)
                    pointB(i)=pointB(i)+repeatDomain(i)
                    pointC(i)=pointC(i)+repeatDomain(i)
                    pointD(i)=pointD(i)+repeatDomain(i)
                    call printVariable( "Duplicate pillar along # at position",i,floor(point(i)))
                    call defineTrapezoidPillarDomain(domainBoolIn,point,pointA,pointB,pointC,pointD,direction,choice_surface,bound)
                    ! domainHold = CSHIFT(domainOrigin,shift=floor(point(i)-hold),dim=i)
                    ! shiftHold=floor(point(i)-hold)
                    ! domainHold = CSHIFT(domainOrigin,shift=shiftHold,dim=i)
                    ! domainBool = domainHold
                    ! domainBool = domainBool.or.domainHold
                    ! exit
                    ! domainBool = CSHIFT(domainOrigin,floor(point(i)-hold),dim=i)
                    ! domainBool = CSHIFT(domainOrigin,shift=10,dim=1)
                enddo

                point(i)=hold
                pointA(i)=holdA
                pointB(i)=holdB
                pointC(i)=holdC
                pointD(i)=holdD

                do while(inBoundFunction6(point,bound))
                    point(i)=point(i)-repeatDomain(i)
                    pointA(i)=pointA(i)-repeatDomain(i)
                    pointB(i)=pointB(i)-repeatDomain(i)
                    pointC(i)=pointC(i)-repeatDomain(i)
                    pointD(i)=pointD(i)-repeatDomain(i)
                    call printVariable( "Duplicate pillar along # at position",i,floor(point(i)))
                    call defineTrapezoidPillarDomain(domainBoolIn,point,pointA,pointB,pointC,pointD,direction,choice_surface,bound)
                    ! shiftHold=floor(point(i)-hold)
                    ! domainHold = CSHIFT(domainOrigin,shift=shiftHold,dim=i)
                    ! domainBool = domainBool.or.domainHold
                    ! domainBool = CSHIFT(domainOrigin,floor(point(i)-hold),dim=i)
                enddo
            endif
        enddo
    endsubroutine





    subroutine generateScalarDomain(outputType,ophase)
        use structure,only: defineCenterDomain,inBoundFunction6,defineRoundPillarDomain,defineParallelpipedPillarDomain,defineTrapezoidPillarDomain ! This is a general purpose structure generator module defined in our library
        implicit none
        ! read(kind=rdp),allocatable,dimension(:,:,:) :: domainOut
        real(kind=rdp),dimension(:,:,:,:),intent(inout),target :: ophase
        real(kind=rdp),dimension(:,:,:),pointer :: dataOut
        real(kind=rdp),dimension(3) :: pointHold,point,pointA,pointB,pointC,pointD,normal,repeatDomain,direction
        integer,intent(in) :: outputType
        real(kind=rdp) :: distance,radius,domainValue
        integer :: i,j,k,ns=0,nf=0,choice_shape,choice_surface,firstLevelCount

        real(kind=rdp),dimension(:,:,:),allocatable :: tempFalse,tempTrue
        integer,dimension(6) :: bound
        integer,dimension(3) :: localBound
        integer :: repeatCount,start,loop
        character(len=:),allocatable :: planeName,columnName
        logical baseSet,repeatDouble

        baseSet=.false.

        allocate(tempTrue(nz,ny,nx))
        allocate(tempFalse(nz,ny,nx))
        tempFalse=0.d0
        tempTrue=1.d0
        planeName="1"
        columnName="1"
        repeatCount = 0
        repeatDouble = .False.

        bound(1)=1
        bound(2)=nx
        bound(3)=1
        bound(4)=ny
        bound(5)=1
        bound(6)=nz

        dataOut=>ophase(1,:,:,:)

        domainLabel=1
        ! print *,"Inside the scalar domain"
        call readFreeFormatOneLine(wholeList,'BASE',domainValue,"The base material index",baseset)
        call readFreeFormatOneLine(wholeList,'SUBTHICK',ns,"Substrate thickness")
        call readFreeFormatOneLine(wholeList,"RANDSEED",j,"The random seed is")
        call readFreeFormatOneLine(wholeList,'FILMTHICK',nf,"Film thickness")

        ! print *,"baseSet",baseSet
        if(baseSet) then
            dataOut=domainValue
            domainLabel=2
            ! print *,"base setting:",domainValue
        else
            call random_seed(j)
            call random_number(dataOut)
        endif



        print *,"dataout",dataOut(20,ny,nx)

        call firstLevelIdentifierCount(wholeList,'PLANE',firstLevelCount)
        do i = 1,firstLevelCount
        repeatCount = 0
        repeatDouble = .False.
        baseSet = .False.
            call printMessage("Creating new plane","-","c")
            call readFreeFormatOneLine(wholeList,i,'PLANE',planeName,"Now processing plane ")
            ! print *,"planeNAme",planeName
            call readFreeFormatOneLine(wholeList,'PLANE',planeName,'POSITION',point(1),point(2),point(3),"Position x,y,z")
            call readFreeFormatOneLine(wholeList,'PLANE',planeName,'NORMAL',normal(1),normal(2),normal(3),"Normal direction")
            call readFreeFormatOneLine(wholeList,'PLANE',planeName,'DISTANCE',distance,"Half width")
            call readFreeFormatOneLine(wholeList,'PLANE',planeName,'REPEAT',repeatDomain(1),repeatDomain(2),repeatDomain(3),"Repeat direction")
            call readFreeFormatOneLine(wholeList,'PLANE',planeName,'REPEATCOUNT',repeatCount,"Amount of repetitions along +(+/-) direction")
            call readFreeFormatOneLine(wholeList,'PLANE',planeName,'REPEATDOUBLE',repeatDouble,"Repeat in both + and - direction")
            call readFreeFormatOneLine(wholeList,'PLANE',planeName,'REGION',bound(1),bound(2),bound(3),bound(4),bound(5),bound(6),"Domain region")
            call readfreeformatoneline(wholelist,'PLANE',planename,'BASE',domainValue,"base domain of plane = ",baseset)
            if (baseSet) then
                dataOut(bound(5):bound(6),bound(3):bound(4),bound(1):bound(2)) = domainValue
            end if

            call readFreeFormatOneLine(wholeList,'PLANE',planeName,'INDEX',domainValue,"Label index")
            domainBool=.false.
            ! print *,"point",point,normal,distance,bound
            ! print *,"size",size(domainBool),domainValue
            localBound(1) = bound(2)-bound(1)+1
            localBound(2) = bound(4)-bound(3)+1
            localBound(3) = bound(6)-bound(5)+1
            allocate(localDomainBool(localBound(3),localBound(2),localBound(1)))
            localDomainBool=.False.
            pointHold = point
            if (repeatDouble) then
                start=0-repeatCount
            else
                start=0
            end if
            do loop = start,repeatCount
            point = pointHold + loop*repeatDomain
            call defineCenterDomain(localDomainBool,point,normal,distance,localBound)
            domainBool(bound(5):bound(6),bound(3):bound(4),bound(1):bound(2)) =localDomainBool.or.domainBool(bound(5):bound(6),bound(3):bound(4),bound(1):bound(2))
            enddo
            

            ! call duplicateDomain(domainBool,point,normal,distance,bound,repeatDomain)


        print *,"dataout",dataOut(20,ny,nx)
            numberedDomain=merge(tempTrue*domainLabel,numberedDomain,domainBool)
            domainLabel=domainLabel+1
            where(domainBool)
                dataOut = domainValue
            end where
            call printMessage("Finished creating plane "//planeName,"-","c")
            deallocate(localDomainBool)
        enddo

        ! print *,"data",dataOut

        repeatCount = 0
        repeatDouble = .False.

        print *,"dataout",dataOut(20,ny,nx)
        call firstLevelIdentifierCount(wholeList,'COLUMN',firstLevelCount)
        do i = 1,firstLevelCount
        repeatCount = 0
        repeatDouble = .False.
        baseSet=.False.
            call printMessage("Creating new column","-","c")
            call readFreeFormatOneLine(wholeList,i,'COLUMN',columnName,"Now processing pillar ")
            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'POSITION',point(1),point(2),point(3),"Position x,y,z")
            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'DIRECTION',direction(1),direction(2),direction(3),"Pillar direction")
            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'SHAPE',choice_shape,"Shape type")
            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'SURFACE',choice_surface,"Surface choice")
            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'RADIUS',radius,"Pillar radius")
            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'POINTA',pointA(1),pointA(2),pointA(3),"PointA")
            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'POINTB',pointB(1),pointB(2),pointB(3),"PointB")
            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'POINTC',pointC(1),pointC(2),pointC(3),"PointC")
            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'POINTD',pointD(1),pointD(2),pointD(3),"PointD")
            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'REPEAT',repeatDomain(1),repeatDomain(2),repeatDomain(3),"Repeat direction")
            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'REPEATCOUNT',repeatCount,"Amount of repetitions along +(+/-) direction")
            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'REPEATDOUBLE',repeatDouble,"Repeat in both + and - direction")
            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'REGION',bound(1),bound(2),bound(3),bound(4),bound(5),bound(6),"Domain region")
            call readfreeformatoneline(wholelist,'COLUMN',planename,'BASE',domainValue,"base domain of Column = ",baseset)
            if (baseSet) then
                dataOut(bound(5):bound(6),bound(3):bound(4),bound(1):bound(2)) = domainValue
            end if

            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'INDEX',domainValue,"Label index")

            domainBool=.false.
            ! print *,"point",point,normal,distance,bound
            ! print *,"size",size(domainBool),domainValue
            localBound(1) = bound(2)-bound(1)+1
            localBound(2) = bound(4)-bound(3)+1
            localBound(3) = bound(6)-bound(5)+1
            allocate(localDomainBool(localBound(3),localBound(2),localBound(1)))
            localDomainBool=.False.
            pointHold = point
            if (repeatDouble) then
                start=0-repeatCount
            else
                start=0
            end if
            do loop = start,repeatCount
            point = pointHold + loop*repeatDomain
            select case(choice_shape)
              case(1)
                ! print *,"round pillar bound: ",bound
                call defineRoundPillarDomain(localDomainBool,point,radius,direction,choice_surface,localBound)
                ! call duplicateDomain(domainBool,point,radius,direction,choice_surface,bound,repeatDomain)
              case (2)
                print *,"for parallelpiped:",point,pointA,pointB
                 print *,"other:",direction,choice_surface,bound
                call defineParallelpipedPillarDomain(domainBool,point,pointA,pointB,direction,choice_surface,localbound)
                ! call duplicateDomain(domainBool,point,pointA,pointB,direction,choice_surface,bound,repeatDomain)
            case(3)
                call defineTrapezoidPillarDomain(domainBool,point,pointA,pointB,pointC,pointD,direction,choice_surface,localbound)
                ! call duplicateDomain(domainBool,point,pointA,pointB,pointC,pointD,direction,choice_surface,bound,repeatDomain)
              case default
            end select
            domainBool(bound(5):bound(6),bound(3):bound(4),bound(1):bound(2)) =localDomainBool.or.domainBool(bound(5):bound(6),bound(3):bound(4),bound(1):bound(2))

            enddo
            ! call duplicateDomain(domainBool,point,bound,repeatDomain)


            numberedDomain=merge(tempTrue*domainLabel,numberedDomain,domainBool)
            domainLabel=domainLabel+1
            where(domainBool)
                dataOut = domainValue
            end where


            call printMessage("Finished creating column "//columnName,"-","c")
            deallocate(localDomainBool)
        enddo

        print *,"dataout",dataOut(20,ny,nx)

        if (ns.ge.0.1) then
            domainValue=0.d0
            call readFreeFormatOneLine(wholeList,'SUBINDEX',domainValue,"Substrate index ")
            dataOut(1:ns,:,:)=domainValue
        end if


        if(nf.gt.0.1) then
            domainValue=0.d0
            call readFreeFormatOneLine(wholeList,'AIRINDEX',domainValue,"Air index ")
            dataOut(ns+nf+1:nz,:,:)=domainValue
        endif

        print *,"dataout",dataOut(20,ny,nx)
        call printMessage("Finished processing structgen.in","-","l")

    end subroutine

    subroutine generateVectorDomain(ophase)
        use structure,only: defineCenterDomain,inBoundFunction6,defineRoundPillarDomain,defineParallelpipedPillarDomain,defineTrapezoidPillarDomain ! This is a general purpose structure generator module defined in our library
        implicit none
        real(kind=rdp),allocatable,dimension(:,:,:) :: domainOut
        real(kind=rdp),dimension(:,:,:),pointer :: data1,data2,data3
        real(kind=rdp),dimension(3) :: domainType,point,pointHold,pointA,pointB,pointC,pointD,normal,repeatDomain,direction
        real(kind=rdp),dimension(:,:,:,:),target,intent(inout) :: ophase
        real(kind=rdp) :: distance,radius
        integer :: i,j,k,ns=0,nf=0,choice_shape,choice_surface,firstLevelCount,repeatCount
        integer,dimension(6) :: bound
        integer,dimension(3) :: localBound
        character(len=:),allocatable :: filename
        real(kind=rdp),dimension(:,:,:),allocatable :: tempFalse,tempTrue
        character(len=300) :: nameHold
        character(len=:),allocatable :: planeName,columnName
        real(kind=rdp) :: hold
        integer loop,start
        logical baseSet,repeatDouble

        baseSet=.false.

        ! firstLevel=size(firstLevelList,1)
        ! secondLevel=size(secondLevelList,1)
        ! print *,"first",firstLevel
        ! print *,"second",secondLevel

        bound(1)=1
        bound(2)=nx
        bound(3)=1
        bound(4)=ny
        bound(5)=1
        bound(6)=nz
        repeatCount = 0
        repeatDouble = .False.


        data1=>ophase(1,:,:,:)
        data2=>ophase(2,:,:,:)
        data3=>ophase(3,:,:,:)
        ! allocate(data1(nz,ny,nx))
        ! allocate(data2(nz,ny,nx))
        ! allocate(data3(nz,ny,nx))

        allocate(tempTrue(nz,ny,nx))
        allocate(tempFalse(nz,ny,nx))
        tempFalse=0.d0
        tempTrue=1.d0



        domainLabel=1

        call readFreeFormatOneLine(wholeList,"BASE",domainType(1),domainType(2),domainType(3),"The base domain is ",baseSet)
        call readFreeFormatOneLine(wholeList,"RANDSEED",j,"The random seed is ")
        call readFreeFormatOneLine(wholeList,'FILMTHICK',nf,"Film thickness = ")
        call readFreeFormatOneLine(wholeList,'SUBTHICK',ns,"Substrate thickness = ")

        ! print *,"baseSet",baseSet
        if(baseSet) then
            data1=domainType(1)
            data2=domainType(2)
            data3=domainType(3)
            domainLabel=2
            ! print *,"base setting:",domainType
        else
            call random_seed(j)
            call random_number(data1)
            call random_number(data2)
            call random_number(data3)
        endif


        call firstLevelIdentifierCount(wholeList,'PLANE',firstLevelCount)
        do i = 1,firstLevelCount
        repeatCount = 0
        repeatDouble = .False.
        baseSet = .False.
            call readFreeFormatOneLine(wholeList,i,'PLANE',planeName,"Now processing plane ")
            call readFreeFormatOneLine(wholeList,'PLANE',planeName,'POSITION',point(1),point(2),point(3),"Position x,y,z = ")
            call readFreeFormatOneLine(wholeList,'PLANE',planeName,'NORMAL',normal(1),normal(2),normal(3),"Normal direction = ")
            call readFreeFormatOneLine(wholeList,'PLANE',planeName,'DISTANCE',distance,"Half width = ")
            call readFreeFormatOneLine(wholeList,'PLANE',planeName,'REGION',bound(1),bound(2),bound(3),bound(4),bound(5),bound(6),"Domain region")
            call readFreeFormatOneLine(wholeList,'PLANE',planeName,'BASE',domainType(1),domainType(2),domainType(3),"Base domain of plane = ",baseSet)
            if (baseSet) then
                data1(bound(5):bound(6),bound(3):bound(4),bound(1):bound(2)) = domaintype(1)
                data2(bound(5):bound(6),bound(3):bound(4),bound(1):bound(2)) = domaintype(2)
                data3(bound(5):bound(6),bound(3):bound(4),bound(1):bound(2)) = domaintype(3)
            end if
            call readFreeFormatOneLine(wholeList,'PLANE',planeName,'DOMAIN',domainType(1),domainType(2),domainType(3),"Polarization value = ")
            call readFreeFormatOneLine(wholeList,'PLANE',planeName,'REPEAT',repeatDomain(1),repeatDomain(2),repeatDomain(3),"Repeat direction = ")
            call readFreeFormatOneLine(wholeList,'PLANE',planeName,'REPEATCOUNT',repeatCount,"Amount of repetitions along +(+/-) direction")
            call readFreeFormatOneLine(wholeList,'PLANE',planeName,'REPEATDOUBLE',repeatDouble,"Repeat in both + and - direction")
            domainBool=.false.
            localBound(1) = bound(2)-bound(1)+1
            localBound(2) = bound(4)-bound(3)+1
            localBound(3) = bound(6)-bound(5)+1
            allocate(localDomainBool(localBound(3),localBound(2),localBound(1)))
            localDomainBool=.False.
            pointHold = point
            if (repeatDouble) then
                start=0-repeatCount
            else
                start=0
            end if
            do loop = start,repeatCount
            point = pointHold + loop*repeatDomain -(/bound(1),bound(3),bound(5)/)

            print *,"loop",loop,repeatDomain
            print *,"point",point
            print *,"localbound",localBound
            call defineCenterDomain(localDomainBool,point,normal,distance,localBound)
            ! print *,"size",size(domainBool(bound(5):bound(6),bound(3):bound(4),bound(1):bound(2))),size(localDomainBool)
            ! print *,"bound",bound,size(domainBool,1),size(domainBool,2),size(domainBool,3)
            ! print *,"bound",bound,size(localDomainBool,1),size(localDomainBool,2),size(localDomainBool,3)
            domainBool(bound(5):bound(6),bound(3):bound(4),bound(1):bound(2)) =localDomainBool.or.domainBool(bound(5):bound(6),bound(3):bound(4),bound(1):bound(2))
            enddo

            ! call duplicateDomain(domainBool,point,normal,distance,bound,repeatDomain)


            numberedDomain=merge(tempTrue*domainLabel,numberedDomain,domainBool)
            domainLabel=domainLabel+1
            where(domainBool)
                data1 = domainType(1)
                data2 = domainType(2)
                data3 = domainType(3)
            end where
            call printMessage("Finished creating plane "//planeName," ","l")
            deallocate(localDomainBool)
        enddo

        repeatCount = 0
        repeatDouble = .False.

        call firstLevelIdentifierCount(wholeList,'COLUMN',firstLevelCount)
        do i = 1,firstLevelCount

        repeatCount = 0
        repeatDouble = .False.
        baseSet = .False.
            call readFreeFormatOneLine(wholeList,i,'COLUMN',columnName,"Now processing pillar ")
            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'POSITION',point(1),point(2),point(3),"Position x,y,z = ")
            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'DIRECTION',direction(1),direction(2),direction(3),"Pillar direction = ")
            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'SHAPE',choice_shape,"Shape type = ")
            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'SURFACE',choice_surface,"Surface choice = ")
            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'RADIUS',radius,"Pillar radius = ")
            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'POINTA',pointA(1),pointA(2),pointA(3),"PointA = ")
            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'POINTB',pointB(1),pointB(2),pointB(3),"PointB = ")
            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'POINTC',pointC(1),pointC(2),pointC(3),"PointC = ")
            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'POINTD',pointD(1),pointD(2),pointD(3),"PointD = ")
            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'REPEAT',repeatDomain(1),repeatDomain(2),repeatDomain(3),"Repeat direction = ")
            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'REGION',bound(1),bound(2),bound(3),bound(4),bound(5),bound(6),"Domain region")

            call readFreeFormatOneLine(wholeList,'COLUMN',planeName,'BASE',domainType(1),domainType(2),domainType(3),"Base domain of column = ",baseSet)
            if (baseSet) then
                data1(bound(5):bound(6),bound(3):bound(4),bound(1):bound(2)) = domaintype(1)
                data2(bound(5):bound(6),bound(3):bound(4),bound(1):bound(2)) = domaintype(2)
                data3(bound(5):bound(6),bound(3):bound(4),bound(1):bound(2)) = domaintype(3)
            end if
            call readFreeFormatOneLine(wholeList,'COLUMN',columnName,'DOMAIN',domainType(1),domainType(2),domaintype(3),"Polarization = ")
            domainBool=.false.
            localBound(1) = bound(2)-bound(1)+1
            localBound(2) = bound(4)-bound(3)+1
            localBound(3) = bound(6)-bound(5)+1
            allocate(localDomainBool(localBound(3),localBound(2),localBound(1)))
            localDomainBool=.False.
            pointHold = point
            if (repeatDouble) then
                start=0-repeatCount
            else
                start=0
            end if
            do loop = start,repeatCount
            point = pointHold + loop*repeatDomain


            select case(choice_shape)
              case(1)
                print *,"round pillar bound: ",bound
                call defineRoundPillarDomain(localDomainBool,point,radius,direction,choice_surface,localBound)
                ! call duplicateDomain(domainBool,point,radius,direction,choice_surface,bound,repeatDomain)
              case (2)
                print *,"for parallelpiped:",point,pointA,pointB
                print *,"other:",direction,choice_surface,bound
                call defineParallelpipedPillarDomain(localDomainBool,point,pointA,pointB,direction,choice_surface,localBound)
                ! call duplicateDomain(domainBool,point,pointA,pointB,direction,choice_surface,bound,repeatDomain)
            case (3)
                call defineTrapezoidPillarDomain(localDomainBool,point,pointA,pointB,pointC,pointD,direction,choice_surface,localBound)
                ! call duplicateDomain(domainBool,point,pointA,pointB,pointC,pointD,direction,choice_surface,bound,repeatDomain)
              case default
            end select
            domainBool(bound(5):bound(6),bound(3):bound(4),bound(1):bound(2)) =localDomainBool.or.domainBool(bound(5):bound(6),bound(3):bound(4),bound(1):bound(2))
            enddo

            ! call duplicateDomain(domainBool,point,bound,repeatDomain)


            numberedDomain=merge(tempTrue*domainLabel,numberedDomain,domainBool)
            domainLabel=domainLabel+1
            where(domainBool)
                data1 = domainType(1)
                data2 = domainType(2)
                data3 = domainType(3)
            end where
            call printMessage("Finished creating column "//columnName," ","l")
            deallocate(localDomainBool)


        enddo

        data1(1:ns,:,:)=0.d0
        data2(1:ns,:,:)=0.d0
        data3(1:ns,:,:)=0.d0
        if(nf.gt.0.1) then
            data1(ns+nf+1:nz,:,:)=0.d0
            data2(ns+nf+1:nz,:,:)=0.d0
            data3(ns+nf+1:nz,:,:)=0.d0
        endif
        ! filename="label.in"
        ! call writeOutput(filename,numberedDomain)




    end subroutine

    subroutine generateComposite(np1,ophase)
        implicit none
        integer:: np01=2     !np01: 1-ellipsoid 2-elliptic cylinder 3-cuboid
        integer:: np02=2     !np02: 1-uniform orientation 2-random orientation
        integer,intent(in):: np1      !np1:  output array type
        logical,parameter:: allowOverlap=.true.
        real(kind=rdp),dimension(:,:,:,:),intent(inout),target :: ophase
        integer iphase(nz,ny,nx)
        real(kind=rdp),dimension(:,:,:),allocatable :: ophaseT   !tuy
        integer i,j,k,l,ii,jj,kk,iii,jjj,kkk
        real ll,mm,nn
        real a1,a2,a3,b1,b2,b3   !tuy
        integer npart0,npart
        real  randn(3)
        real,parameter::  pi=acos(-1.)
        real  phiT,thetaT,psiT,vaxis(3,3)
        real(kind=rdp),dimension(:,:,:),pointer :: data1,data2,data3
        logical exist
        character(len=300),dimension(:,:),allocatable:: firstLevelList
        integer firstLevel

        ! np1=1

        allocate(ophaseT(nz,ny,nx))
        data1=>ophase(1,:,:,:)
        data2=>ophase(2,:,:,:)
        data3=>ophase(3,:,:,:)


        call getFirstLevelList(wholeList,firstLevelList)
        firstLevel = size(firstLevelList,dim=1)

        do i = 1,firstLevel
            select case (trim(firstLevelList(i,1)))
              case("SHAPE")
                read(firstLevelList(i,2),*) np01
                write(*,'(a80,I10)') 'The particle shape = ',np01
              case("ORIENTATION")
                read(firstLevelList(i,2),*) np02
                write(*,'(a80,I10)') 'The orientation type = ',np02
!    case("OUTPUT")
!        read(firstLevelList(i,2),*) np1
!        write(*,'(a80,I10)') 'The output array type = ',np1
              case("NPART0")
                read(firstLevelList(i,2),*) npart0
                write(*,'(a80,I10)') 'The total number of particles = ',npart0
              case("NPART")
                read(firstLevelList(i,2),*) npart
                write(*,'(a80,I10)') 'The total number of particles =', npart
              case("PARTSIZE")
                read(firstLevelList(i,2),*) a1,a2,a3
                write(*,'(a80,3(F10.3))') 'Size of particles (half-axis length) = ', a1,a2,a3
              case("SHELLPARTSIZE")
                read(firstLevelList(i,2),*) b1,b2,b3
                write(*,'(a80,3(F10.3))') 'Size of particles + shell (half-axis length) = ', a1,a2,a3
              case default
            end select
        enddo






        ophase=0.

        iphase=1   !tuy

        call random_seed()

        if (np02==1) then

            l=0
            do while (npart.lt.npart0)
                l=l+1

                ophaseT=0.
                exist=.true.
                call random_number(randn)
                i=mod(int(randn(1)*100*nx),nx)+1  !
                j=mod(int(randn(2)*100*ny),ny)+1  !
                k=mod(int(randn(3)*100*nz),nz)+1  !

                do ii=i-a1,i+a1
                    do jj=j-a2,j+a2
                        do kk=k-a3,k+a3
                            if ((np01==1.and.(((ii-i)*1./a1)**2+((jj-j)*1./a2)**2+((kk-k)*1./a3)**2 < 1.))&
                                .or.(np01==2.and.(((ii-i)*1./a1)**2+((jj-j)*1./a2)**2 < 1.))&
                                .or.(np01==3)) then
                                iii=mod(ii-1+nx,nx)+1
                                jjj=mod(jj-1+ny,ny)+1
                                kkk=mod(kk-1+nz,nz)+1
                                if ((.not.allowOverlap).and.ophase(3,iii,jjj,kkk)>0.5) then   !tuy
                                    exist=.false.
                                    goto 199
                                endif
                                ophaseT(iii,jjj,kkk)=1.
                            endif
                        enddo
                    enddo
                enddo

199             if (exist) then
                    npart=npart+1
                    write (99,*) npart,l
                    do ii=i-a1,i+a1
                        do jj=j-a2,j+a2
                            do kk=k-a3,k+a3
                                iii=mod(ii-1+nx,nx)+1
                                jjj=mod(jj-1+ny,ny)+1
                                kkk=mod(kk-1+nz,nz)+1
                                ophase(3,iii,jjj,kkk)=min(1.,ophase(3,iii,jjj,kkk)+ophaseT(iii,jjj,kkk))
                            enddo
                        enddo
                    enddo

                    do ii=i-b1,i+b1   !tuyb
                        do jj=j-b2,j+b2
                            do kk=k-b3,k+b3
                                if ((np01==1.and.(((ii-i)*1./b1)**2+((jj-j)*1./b2)**2+((kk-k)*1./b3)**2 < 1.))&
                                    .or.(np01==2.and.(((ii-i)*1./b1)**2+((jj-j)*1./b2)**2 < 1.))&
                                    .or.(np01==3)) then
                                    iii=mod(ii-1+nx,nx)+1
                                    jjj=mod(jj-1+ny,ny)+1
                                    kkk=mod(kk-1+nz,nz)+1
                                    ophase(2,iii,jjj,kkk)=1.
                                endif
                            enddo
                        enddo
                    enddo   !tuyf
                endif

            enddo

        elseif (np02==2) then

            l=0
            do while (npart.lt.npart0)
                l=l+1

                ophaseT=0.
                exist=.true.
                call random_number(randn)
                i=mod(int(randn(1)*100*nx),nx)+1
                j=mod(int(randn(2)*100*ny),ny)+1
                k=mod(int(randn(3)*100*nz),nz)+1

                call random_number(randn)
                phiT=randn(1)*2*pi
                thetaT=acos(randn(2)*2.-1.)
                psiT=randn(3)*2*pi

                vaxis(1,1)=cos(phiT)*cos(psiT)-cos(thetaT)*sin(phiT)*sin(psiT)
                vaxis(1,2)=sin(phiT)*cos(psiT)+cos(thetaT)*cos(phiT)*sin(psiT)
                vaxis(1,3)=sin(psiT)*sin(thetaT)

                vaxis(2,1)=-cos(thetaT)*sin(phiT)*cos(psiT)-cos(phiT)*sin(psiT)
                vaxis(2,2)=cos(thetaT)*cos(phiT)*cos(psiT)-sin(phiT)*sin(psiT)
                vaxis(2,3)=cos(psiT)*sin(thetaT)

                vaxis(3,1)=sin(phiT)*sin(thetaT)
                vaxis(3,2)=-cos(phiT)*sin(thetaT)
                vaxis(3,3)=cos(thetaT)

                do ll=-a1,a1,0.7
                    do mm=-a2,a2,0.7
                        do nn=-a3,a3,0.7
                            if ((np01==1.and.((ll*1./a1)**2+(mm*1./a2)**2+(nn*1./a3)**2 < 1.))&
                                .or.(np01==2.and.((ll*1./a1)**2+(mm*1./a2)**2 < 1.))&
                                .or.(np01==3)) then
                                ii=i+ll*vaxis(1,1)+mm*vaxis(2,1)+nn*vaxis(3,1)
                                jj=j+ll*vaxis(1,2)+mm*vaxis(2,2)+nn*vaxis(3,2)
                                kk=k+ll*vaxis(1,3)+mm*vaxis(2,3)+nn*vaxis(3,3)
                                iii=mod(ii-1+nx,nx)+1
                                jjj=mod(jj-1+ny,ny)+1
                                kkk=mod(kk-1+nz,nz)+1
                                if ((.not.allowOverlap).and.ophase(3,iii,jjj,kkk)>0.5) then   !tuy
                                    exist=.false.
                                    goto 299
                                endif
                                ophaseT(iii,jjj,kkk)=1.
                            endif
                        enddo
                    enddo
                enddo

299             if (exist) then
                    npart=npart+1
                    write (99,*) npart,l
                    do ii=i-(a1*abs(vaxis(1,1))+a2*abs(vaxis(2,1))+a3*abs(vaxis(3,1))),&
                        i+(a1*abs(vaxis(1,1))+a2*abs(vaxis(2,1))+a3*abs(vaxis(3,1)))
                        do jj=j-(a1*abs(vaxis(1,2))+a2*abs(vaxis(2,2))+a3*abs(vaxis(3,2))),&
                            j+(a1*abs(vaxis(1,2))+a2*abs(vaxis(2,2))+a3*abs(vaxis(3,2)))
                            do kk=k-(a1*abs(vaxis(1,3))+a2*abs(vaxis(2,3))+a3*abs(vaxis(3,3))),&
                                k+(a1*abs(vaxis(1,3))+a2*abs(vaxis(2,3))+a3*abs(vaxis(3,3)))
                                iii=mod(ii-1+nx,nx)+1
                                jjj=mod(jj-1+ny,ny)+1
                                kkk=mod(kk-1+nz,nz)+1
                                ophase(3,iii,jjj,kkk)=min(1.,ophase(3,iii,jjj,kkk)+ophaseT(iii,jjj,kkk))   !tuy
                            enddo
                        enddo
                    enddo

                    do ll=-b1,b1,0.7   !tuyb
                        do mm=-b2,b2,0.7
                            do nn=-b3,b3,0.7
                                if ((np01==1.and.((ll*1./b1)**2+(mm*1./b2)**2+(nn*1./b3)**2 < 1.))&
                                    .or.(np01==2.and.((ll*1./b1)**2+(mm*1./b2)**2 < 1.))&
                                    .or.(np01==3)) then
                                    ii=i+ll*vaxis(1,1)+mm*vaxis(2,1)+nn*vaxis(3,1)
                                    jj=j+ll*vaxis(1,2)+mm*vaxis(2,2)+nn*vaxis(3,2)
                                    kk=k+ll*vaxis(1,3)+mm*vaxis(2,3)+nn*vaxis(3,3)
                                    iii=mod(ii-1+nx,nx)+1
                                    jjj=mod(jj-1+ny,ny)+1
                                    kkk=mod(kk-1+nz,nz)+1
                                    ophase(2,iii,jjj,kkk)=1.
                                endif
                            enddo
                        enddo
                    enddo   !tuyf

                endif

            enddo

        endif                                  !np02


        print *,"ophawse",size(ophase)
        ophase(2,:,:,:)=min(ophase(2,:,:,:),1.d0-ophase(3,:,:,:))
        ophase(1,:,:,:)=1.-ophase(2,:,:,:)-ophase(3,:,:,:)

        do k=1,nz
            do j=1,ny
                do i=1,nx
                    iphase(i,j,k)=1
                    do l=1,3   !tuy
                        if (ophase(l,i,j,k)>ophase(iphase(i,j,k),i,j,k)) iphase(i,j,k)=l
                    enddo
                enddo
            enddo
        enddo

        if(np1.eq.1) then
            data1=ophase(1,:,:,:)
            data2=ophase(2,:,:,:)
            data3=ophase(3,:,:,:)
        else if(np1.eq.2) then
            data1=iphase
        endif
        !      write(*,300),nx,ny,nz,npart,sum(dble(ophase(1,:,:,:)))/(nx*ny*nz),sum(dble(ophase(2,:,:,:)))/(nx*ny*nz),sum(dble(ophase(3,:,:,:)))/(nx*ny*nz)   !tuy
        !
        !      open(unit=1,file='structgen.in')
        !
        !      write(1,300),nx,ny,nz,npart,sum(dble(ophase(1,:,:,:)))/(nx*ny*nz),sum(dble(ophase(2,:,:,:)))/(nx*ny*nz),sum(dble(ophase(3,:,:,:)))/(nx*ny*nz)   !tuy
        !
        !      if (np1.eq.1) then
        !        do i=1,nx
        !        do j=1,ny
        !        do k=1,nz
        !          write(1,100),i,j,k,ophase(1,i,j,k),ophase(2,i,j,k),ophase(3,i,j,k)   !tuy
        !        enddo
        !        enddo
        !        enddo
        !
        !      elseif (np1.eq.2) then
        !        do i=1,nx
        !        do j=1,ny
        !        do k=1,nz
        !          write(1,200),i,j,k,iphase(i,j,k)
        !        enddo
        !        enddo
        !        enddo
        !
        !      endif
        !
        !      close(1)

100     format(3(i6),12(f8.3))
200     format(4(i6),12(f8.3))
300     format(3(i6),"   ! System size      ",i6,"   ! # of particles      ",3(f10.4),"   !phase fractions" )





    end subroutine


end module

program generateStructure
    use mod_Struct_Gen
    use free_format
    use print_utilities
    use mod_interfaces
    use,intrinsic :: ISO_Fortran_env
    implicit none
    real(kind=rdp),allocatable,dimension(:,:,:,:),target :: ophase
    integer,allocatable,dimension(:,:,:):: iphase
    integer :: iounit,i,j,k,ns,nf
    character(len=:),allocatable :: filename,versionNumber
    character(len=300) :: stringHold
    logical,dimension(:,:,:),allocatable :: domain
    character(len=:),allocatable :: choiceStructure,identifier,nameHold
    ! character(len=80) :: filename
    integer :: outputType,moduleInt,rank,process


    call MPI_INIT(ierr)
    call MPI_comm_size(MPI_COMM_WORLD,process,ierr)
    call MPI_comm_rank(MPI_COMM_WORLD,rank,ierr)

    moduleInt=1
    versionNumber="1.1.6"//char(0)

    !call checkValidity(versionNumber,moduleInt,0,rank)
    call byPassCheckValidity
    call printMessage("-","-","c")
    call printMessage("*","*","c")
    call printMessage("Sturcture Generator","*","c")
    call printMessage("This is a tool for the MUPRO package","*","c")
    call printMessage("*","*","c")
    call printMessage("-","-","c")
    call printMessage("Start to read file structgen.in","-","l")

    filename="structgen.in"
    identifier='FILENAME'

    outputType = 2
    call parseFreeFormatFile(filename,wholeList)

    call printMessage("System general setup","-","l")
    call readFreeFormatOneLine(wholeList,1,identifier,nameHold,"The output structure file name is ")
    call readFreeFormatOneLine(wholeList,'SIMDIM',nx,ny,nz,"System dimension x,y,z ")
    call readFreeFormatOneLine(wholeList,1,'SYSTYPE',choiceStructure,"The choice of output structure type is ")

    call printMessage("-","-","c")
    call printMessage("Some necessary allocation","-","c")
    call muproAllocate3D(numberedDomain,nz,ny,nx,"numberedDomain",memory)
    call muproAllocate3D(domainBool,nz,ny,nx,"domainBool",memory)
    bound=(/nx,ny,nz/)

    call muproAllocate4D(ophase,3,nz,ny,nx,"ophase",memory)
    call muproAllocate3D(iphase,nz,ny,nx,"iphase",memory)
    call printMessage("-","-","c")

    ! print *,"after the allocation",choiceStructure

    select case(choiceStructure)
      case("FERRO")
        call printMessage("Creating ferroelectric polar vector domains ","-","l")
        call generateVectorDomain(ophase)
        filename=trim(nameHold)
        call writeOutput(filename,ophase(1,:,:,:),ophase(2,:,:,:),ophase(3,:,:,:),ophase(1,:,:,:),ophase(2,:,:,:),ophase(3,:,:,:))
      case("INHOMO")
        call printMessage("Creating the inhomogeneous material distribution ","-","l")
        call generateScalarDomain(outputType,ophase)
        call printMessage("Domain distribution is defined, now writing output file ","-","l")
        filename=trim(nameHold)
        if(outputType.eq.1) then
            call writeOutput(filename,ophase)
        else if(outputType.eq.2) then
            iphase=ophase(1,:,:,:)
            call writeOutput(filename,ophase(1,:,:,:))
        endif
      case("COMPOSITE")
        call printMessage("Creating composite structure ","-","l")
        call generateComposite(outputType,ophase)
        filename=trim(nameHold)
        if(outputType.eq.1) then
            call writeOutput(filename,ophase)
        else if(outputType.eq.2) then
            iphase=ophase(1,:,:,:)
            call writeOutput(filename,iphase)
        endif
      case default
    end select
    !call defineCenterDomain(domain,point2,normal,distance,bound)
    !call defineCenterDomain(domain,point3,normal,distance,bound)
    ! domainOut = domainOut+merge(tempTrue,tempFalse,domain)
    ! data1(ns+1:ns+nf,:,:) = domainType(1)*domainOut(ns+1:ns+nf,:,:)
    ! data2(ns+1:ns+nf,:,:) = domainType(2)*domainOut(ns+1:ns+nf,:,:)
    ! data3(ns+1:ns+nf,:,:) = domainType(3)*domainOut(ns+1:ns+nf,:,:)

    call printMessage("-","-","c")
    call printMessage("*","*","c")
    call printMessage("Structure generator finished","-",'c')
    call printMessage("*","*","c")
    call printMessage("-","-","c")


    call MPI_Barrier(MPI_COMM_WORLD,ierr)
    call MPI_Finalize(ierr)
end program
