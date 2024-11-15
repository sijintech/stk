__author__ = 'xuc116'
#%%
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable

fileName = "PELOOP15.dat"
outputFile = "PELOOP15"
nx=128
ny=128
PEdata = pd.read_csv(fileName,header=None,skiprows=0,delim_whitespace=True)
PEdata.columns = ['x','y','1','2','3','4']

#%%
x = PEdata[[0]]
y = PEdata[[1]]
U = PEdata[[2]]
V = PEdata[[3]]

data = PEdata.iloc[:,-1].values
data = np.asarray(map(float,(i for i in data)))
data = data.reshape((ny,nx),order='F')

#%% plot the vector field of polarization
plt.figure(figsize=(nx/10,ny/10))
ax = plt.subplot(111)

N = np.sqrt(U.values**2+V.values**2)/20
vector = plt.quiver(x,y,U,V,units='xy',scale=0.75,width=0.1,headwidth=4,headlength=5,headaxislength=5)

heat = ax.imshow(data,origin='lower')
divider = make_axes_locatable(ax)
cax = divider.append_axes("right",size="5%",pad=0.05)
plt.colorbar(heat,cax=cax)

outname = outputFile+'.png'
plt.savefig(outname,dpi=500)
