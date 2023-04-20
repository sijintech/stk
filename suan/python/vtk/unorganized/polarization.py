__author__ = 'xuc116'
#%%
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable


#%% This is where the input parameters are
index = 0
slicePlane = 'z'
sliceNum = 27
fileindex = 0
polar=[1,1,1,1,1,1,1,1,1]
scalar=[1,1,1,1,1,1,1,0,0]
scalarLength=[1,1,1,6,6,6,6,0,0]
drive=[0,0,0,0,0,0,0,1,0]
gen=[0,0,0,0,0,0,0,0,1]
path='./larger1/'
outpath='./larger1/mid/'

#%%
for fileindex in range(3,4):
    vectorFlag = polar[fileindex]
    heatFlag = scalar[fileindex]
    driveFlag = drive[fileindex]
    genFlag = gen[fileindex]
    filelist=['Grade_En','Elect_En','Elast_En','strain','Elas_Str','Eign_Str','stress','Gen_For','Eflexo']
    iname = str("{0:08d}".format(index))
    iname1=str("{0:08d}".format(index+1))
    fileName = path+'PELOOP.'+iname+'.dat'
    fileName1 = path+filelist[fileindex]+'.'+iname1+'.dat'
    fileName2 = path+filelist[fileindex]+'.'+iname1+'.dat'
    GenX = path+'Gen_ForX.'+iname1+'.dat'
    GenY = path+'Gen_ForY.'+iname1+'.dat'
    GenZ = path+'Gen_ForZ.'+iname1+'.dat'
    fileName3 = [GenX,GenY,GenZ]
    components=[1]
    if heatFlag:
        components=range(1,scalarLength[fileindex]+1)
    if driveFlag:
        components=range(1,4)
    if genFlag:
        components=range(1,4)

    print(components)
    #%%-----------------------------------------------------
    # Import the data into an array PEdata
    #-------------------------------------------------------
    dimension = pd.read_fwf(fileName,header=None)
    nx = int(dimension.iloc[0,0])
    ny = int(dimension.iloc[0,1])
    nz = int(dimension.iloc[0,2])

    if slicePlane=='x':
        n = [ny,nz]
    elif slicePlane=='y':
        n = [nx,nz]
    elif slicePlane=='z':
        n = [nx,ny]

    if vectorFlag==1:
        PEdata = pd.read_csv(fileName,sep='\s*',header=None,skiprows=1)
        PEdata.columns = ['x','y','z','px','py','pz','pxl','pyl','pzl']
        if slicePlane=='x':
            PEdata = PEdata.loc[PEdata.x==sliceNum,['y','z','py','pz']]
        elif slicePlane=='y':
            PEdata = PEdata.loc[PEdata.y==sliceNum,['x','z','px','pz']]
        elif slicePlane=='z':
            PEdata = PEdata.loc[PEdata.z==sliceNum,['x','y','px','py']]


    if heatFlag==1:
        HEATdata = pd.read_fwf(fileName1,header=None,skiprows=1)
        if (fileindex in [0,1,2]):
            HEATdata.columns = ['x','y','z','1']
        else:
            HEATdata.columns = ['x','y','z','1','2','3','4','5','6']

    if driveFlag==1:
        HEATdata = pd.read_fwf(fileName2,header=None,skiprows=1)
        HEATdata.columns = ['x','y','z','1','2','3']


    for component in components:
        component=str(component)
        if heatFlag==1:
            #HEATdata.columns = ['x','y','z','1','2','3']
            if slicePlane=='x':
                HEATdata = HEATdata.loc[HEATdata.x==sliceNum,[component]].values
                HEATdata = HEATdata.reshape((nz,ny),order='F')
                n = [ny,nz]
            elif slicePlane=='y':
                HEATdata = HEATdata.loc[HEATdata.y==sliceNum,[component]].values
                HEATdata = HEATdata.reshape((nz,nx),order='F')
                n = [nx,nz]
            elif slicePlane=='z':
                data = HEATdata.loc[HEATdata.z==sliceNum,component].values
                data = np.asarray(map(float,(i for i in data)))
                data = data.reshape((ny,nx),order='F')
                n = [nx,ny]

        if driveFlag==1:

            if slicePlane=='x':
                HEATdata = HEATdata.loc[HEATdata.x==sliceNum,[component]].values
                HEATdata = HEATdata.reshape((nz,ny),order='F')
                n = [ny,nz]
            elif slicePlane=='y':
                HEATdata = HEATdata.loc[HEATdata.y==sliceNum,[component]].values
                HEATdata = HEATdata.reshape((nz,nx),order='F')
                n = [nx,nz]
            elif slicePlane=='z':
                data = HEATdata.loc[HEATdata.z==sliceNum,component].values
                data = np.asarray(map(float,(i for i in data)))
                data = data.reshape((ny,nx),order='F')
                n = [nx,ny]

        if genFlag!=0:
            genFlag=str(genFlag)
            HEATdata = pd.read_fwf(fileName3[int(component)-1],header=None,skiprows=1)
            HEATdata.columns = ['x','y','z','1','2','3','4','5','6']
            #HEATdata.columns = ['x','y','z','elas','elec','land','grad','chem','all']
            if slicePlane=='x':
                HEATdata = HEATdata.loc[HEATdata.x==sliceNum,[genFlag]].values
                HEATdata = HEATdata.reshape((nz,ny),order='F')
                n = [ny,nz]
            elif slicePlane=='y':
                HEATdata = HEATdata.loc[HEATdata.y==sliceNum,[genFlag]].values
                HEATdata = HEATdata.reshape((nz,nx),order='F')
                n = [nx,nz]
            elif slicePlane=='z':
                data = HEATdata.loc[HEATdata.z==sliceNum,genFlag].values
                data = np.asarray(map(float,(i for i in data)))
                data = data.reshape((ny,nx),order='F')
                n = [nx,ny]

        #%%
        if vectorFlag==1:
            x = PEdata[[0]]
            y = PEdata[[1]]
            U = PEdata[[2]]
            V = PEdata[[3]]

        if heatFlag==1 or driveFlag==1 or genFlag!=0:
            print(data.shape)


        #%% plot the vector field of polarization
        plt.figure(figsize=(n[0]/10,n[1]/10))
        ax = plt.subplot(111)

        if vectorFlag==1:
            N = np.sqrt(U.values**2+V.values**2)/20
            vector = plt.quiver(x,y,U,V,units='xy',width=0.2,headwidth=2,headlength=2,headaxislength=1.5)

        if heatFlag==1 or driveFlag==1 or genFlag!=0:
            heat = ax.imshow(data,origin='lower')
            divider = make_axes_locatable(ax)
            cax = divider.append_axes("right",size="5%",pad=0.05)
            plt.colorbar(heat,cax=cax)

        outname = outpath+filelist[fileindex]+component+"."+str(index)+'.png'
        plt.savefig(outname,dpi=500)
