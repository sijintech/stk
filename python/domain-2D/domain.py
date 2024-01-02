# %%
import numpy as np
import pandas as pd

from cxx import *
from yyp_helper import *

import random
import matplotlib
import matplotlib.colors
import matplotlib.pyplot as plt
import matplotlib.patheffects as PathEffects
import matplotlib.gridspec as gridspec

import os
import glob
import datetime 

import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


from IPython.core.display import display, HTML
display(HTML("<style>.container { width:90% !important; }</style>"))

from decimal import Decimal
import imageio
import ipywidgets as widgets
import json

# %%
matplotlib.rcParams['font.family'] = 'sans-serif'
matplotlib.rcParams['font.sans-serif'] = ['Helvetica']
matplotlib.rcParams['pdf.fonttype'] = 42
matplotlib.rcParams['ps.fonttype'] = 42
matplotlib.rcParams['font.size'] = 17

# %%
def read_inputs(path_of_folder):
    '''
    Read the input.in, pot.in and *.pbs of each folder. 
    
    '''
    if path_of_folder[-1] != '/':
        path_of_folder = path_of_folder + '/'
        
    with open(path_of_folder + 'input.in') as f:
        inputIn = f.read().splitlines()

    inputIn = [item for item in inputIn if item != ""]
    inputIn = [item.split(' = ') for item in inputIn if item[0] != "#"]
    inputIn = {d[0]: d[1] for d in inputIn}

    with open(glob.glob(path_of_folder + '*.pbs')[0]) as f:
        helloPBS = f.read().splitlines()
        
    helloPBS = [item.split() for item in helloPBS if '#PBS' in item]
    helloPBS = {'PBS' + d[1]: d[2] for d in helloPBS}
        
    with open(path_of_folder + 'pot.in', "r") as f:
        potIn = json.load(f)
    
    inputIn['JobFolder'] = path_of_folder.split('/')[-2]
    
    return {**inputIn, **helloPBS, **potIn}


def expLatex(x):
    return x.replace('*10^', 'e')

def plotDomains(file, thresh, layer, rangeZ=(12, 32)):
    dftmp = pfDat_to_df(file)[['gx', 'gy', 'gz']].describe()
    maxOdPara = abs(dftmp.loc[['min', 'max'],:].values).max()
    
    df = readDatFerroDomain(file, thresh, 180)
    
#    plt.style.use('dark_background')

    plt.figure(figsize=(11.5, 11))
    gs = gridspec.GridSpec(1, 2,width_ratios=[6,1])
    
    plt.subplot(gs[0])
    plt.pcolormesh(df[:,:,layer].T, cmap =cmap, norm=norm, vmin = -1, vmax = 26)
    plt.rc('xtick', labelsize=17)
    plt.rc('ytick', labelsize=17)
    #    plt.axes().set_aspect('equal', 'datalim')
    plt.title(file.split('/')[-1], fontsize = 20)
    
#    cb = plt.colorbar(ticks = [ 0.2,  1,  2,  3,  4,  5,  6,  7,  8,  9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 25.8])
#    cb.ax.set_yticklabels(domainTypeLabel)

    plt.xlabel('X site', fontsize=17)
    plt.ylabel('Y site', fontsize=17)
    
    inputs = read_inputs('/'.join(file.split('/')[:-1]))
    caption = '/'.join(file.split('/')[-3:]) + '\n'       
    caption = caption + "Max: {:.3g}; Threshold: {}; Layer: {};".format(maxOdPara, thresh, 12) + '\n'
    
    try:
        caption = caption + '; '.join([str(a) + " = " +  inputs[a] for a in ["TEM", "MISFIT", "MATERIAL.DIELECON"]]) + '\n'
    except KeyError:
        caption = caption + '; '.join([str(a) + " = " +  inputs[a] for a in ["TEM", "MISFIT", ]]) + '\n'
    
    
    caption = caption + '; '.join([str(a) + " = " +  inputs[a] for a in ["PNOISMAG", "QNOISMAG"]]) + '\n'
    caption = caption + '; '.join([str(a) + " = " +  inputs[a] for a in ["MATERIAL.GRADPCON", "MATERIAL.GRADQCON"]]) + '\n'

    caption = caption.replace('MATERIAL.', '')
    caption = caption + "Normalizer: " + str(inputs['Normalizer'])  + '\n'
    caption = caption + "Polar: " + expLatex(inputs['Landau']['a1']) + ', ' + \
                         expLatex(inputs['Landau']['a11']) + ', ' + expLatex(inputs['Landau']['a12'])  + '\n'

    try:
        caption = caption + "OctaTilt: " + expLatex(inputs['OctahedralRotation']['b1']) + ', ' + \
                         expLatex(inputs['OctahedralRotation']['b11']) + ', ' + expLatex(inputs['OctahedralRotation']['b12'])  + '\n'
    except KeyError:
        caption = caption + "OctaTilt: " + expLatex(inputs['OctahedralRotation']['b1']) + ', ' + \
                         expLatex(inputs['OctahedralRotation']['b11']) + ', ' + expLatex(inputs['OctahedralRotation']['b22'])  + '\n'        

    caption = caption + "Electrostrictive: " + expLatex(inputs['Electrostrictive']['Q11']) + ', ' + \
                         expLatex(inputs['Electrostrictive']['Q12']) + ', ' + expLatex(inputs['Electrostrictive']['Q44'])  + ';  '

    caption = caption + "ElasticStiffness: " + expLatex(inputs['ElasticStiffness']['C11']) + ', ' + \
                         expLatex(inputs['ElasticStiffness']['C12']) + ', ' + expLatex(inputs['ElasticStiffness']['C44'])  + '\n'

    caption = caption + "Rotostrictive: " + expLatex(inputs['Rotostrictive']['L11']) + ', ' + \
                         expLatex(inputs['Rotostrictive']['L12']) + ', ' + expLatex(inputs['Rotostrictive']['L44'])  + ';  '

    caption = caption + "PolarRotoCoupling: " + expLatex(inputs['PolarRotoCoupling']['t11']) + ', ' + \
                         expLatex(inputs['PolarRotoCoupling']['t12']) + ', ' + expLatex(inputs['PolarRotoCoupling']['t44'])  + '\n'


    caption = caption.lower()
    
    
    vertical_offset = -55; 
    if df.shape[0] > 128:
        vertical_offset = -100; 
    plt.text(0, vertical_offset, caption, fontsize = 13)
    
    plt.subplot(gs[1])
    unique, counts = np.unique(df[:,:,rangeZ[0]:rangeZ[1]].reshape(-1), return_counts=True)
    counts = counts/counts.sum()*100
    
    arr = np.zeros(27)
    for i in range(len(unique)):
        arr[int(unique[i])] = counts[i]

    barlist = plt.barh(domainTypeLabel, arr)
    for i in range(len(barlist)):
        barlist[i].set_color(crr[i])

    plt.title('Composite', fontsize = 17)
    plt.xlabel('Percentage', fontsize = 17)
    plt.xlim(0, 30)
    

    plt.tight_layout()
    
    exportFolder = '/'.join((file).split('/')[:-1]) + '/' + (file).split('/')[-1].split('.')[0] + '_png/'
    if os.path.exists(exportFolder):
        print('Export folder exists')
    else:
        os.mkdir(exportFolder)

        
    plt.savefig(exportFolder + (file).split('/')[-1][:-3] + 'png', dpi=100,  transparent=True)
    return df

# %%
def on_change(change):
    if change['type'] == 'change' and change['name'] == 'value':
        print ("changed to %s" % change['new'], end='\r')

# %% [markdown]
# # Pick folder here

# %%
phaseSet = widgets.Select(options=sorted(glob.glob('/Volumes/Arcturus/Expt/PSU/STO/*')), 
                          rows=20, description='Folder:', disabled=False, )

#phaseSet = widgets.Select(options=sorted(glob.glob('/Users/yun-yi/Desktop/*')), rows=12, description='Folder:', disabled=False, )
phaseSet.layout.width = '1000px'
display(phaseSet)
phaseSet.observe(on_change)

# %% [markdown]
# # Pick a subfolder or loop over subfolders

# %%
list_of_leaves = sorted(glob.glob(phaseSet.value + '/*'))
list_of_leaves = [leaf for leaf in list_of_leaves if os.path.isdir(leaf)]

hello = widgets.Select(options=list_of_leaves,rows=10, description='Folder:', disabled=False, )
hello.layout.width = '1000px'
display(hello)
hello.observe(on_change)

# %%
for leaf in list_of_leaves:
    print(leaf)
    path = leaf
    cmap = matplotlib.colors.ListedColormap(crr); norm = matplotlib.colors.BoundaryNorm(boundaries, cmap.N, clip=True)

    fileInstance = sorted(glob.glob(path + '/Polar*.dat'))[-1]
    dfp = plotDomains(fileInstance, 1e-1, 12, (12, 32))

    fileInstance = sorted(glob.glob(path + '/OctaTilt*.dat'))[-1]
    dfo = plotDomains(fileInstance, 1e-12, 12, (12, 32))
    
    

from shutil import copyfile
copyList = sorted(glob.glob(phaseSet.value + '/*/*/Octa*.png'))
for file in copyList:
    copyfile(file, 
             '/'.join(file.split('/')[:-3]) + '/' + 'O' + file.split('/')[-3] + file.split('/')[-1])

copyList = sorted(glob.glob(phaseSet.value + '/*/*/Polar*.png'))
for file in copyList:
    copyfile(file, 
             '/'.join(file.split('/')[:-3]) + '/' + 'P' + file.split('/')[-3] + file.split('/')[-1])


# %% [markdown]
# # Read just one

# %%
path = hello.value; print(path)

cmap = matplotlib.colors.ListedColormap(crr); norm = matplotlib.colors.BoundaryNorm(boundaries, cmap.N, clip=True)

fileInstance = sorted(glob.glob(path + '/Polar*.dat'))[-1]
dfp = plotDomains(fileInstance, 1e-1, 31, (12, 32))

fileInstance = sorted(glob.glob(path + '/OctaTilt*.dat'))[-1]
dfo = plotDomains(fileInstance, 1e-12, 31, (12, 32))

# %%
path = hello.value; print(path)
fileInstance = sorted(glob.glob(path + '/OctaTilt*'))
fileInstance
cmap = matplotlib.colors.ListedColormap(crr); norm = matplotlib.colors.BoundaryNorm(boundaries, cmap.N, clip=True)


# %%
plotDomains('/Volumes/Arcturus/Expt/PSU/STO/23_Seed_Field/01_Field_A/OctaTilt.in', 1e-12, 31, (12, 32))

# %%
plotDomains('/Volumes/Arcturus/Expt/PSU/STO/23_Seed_Field/02_Dielectric_Off/OctaTilt.in', 1e-12, 31, (12, 32))

# %%
from shutil import copyfile
copyList = sorted(glob.glob(phaseSet.value + '/*/*/Octa*.png'))
for file in copyList:
    copyfile(file, 
             '/'.join(file.split('/')[:-3]) + '/' + 'O' + file.split('/')[-3] + file.split('/')[-1])

copyList = sorted(glob.glob(phaseSet.value + '/*/*/Polar*.png'))
for file in copyList:
    copyfile(file, 
             '/'.join(file.split('/')[:-3]) + '/' + 'P' + file.split('/')[-3] + file.split('/')[-1])

# %% [markdown]
# # Octa Tilt x 1e12 for the MuVis

# %%
for file in sorted(glob.glob(hello.value + '/OctaTilt*.dat')[-1:]):
    print('Processing:',  file, '...')
    df = pdDat_to_list(file)

    dimension = list(map(int, df[1]))
    head  = str(dimension[0]).rjust(6) + str(dimension[1]).rjust(6) + str(dimension[2]).rjust(6) + '\n'

    f = open(file[:-3] +'pm', "w")
    f.write(head)

    mul = 1e12;

    for line in df[0]:
            coord = str(int(line[0])).rjust(6) + str(int(line[1])).rjust(6) + str(int(line[2])).rjust(6) 

            polar = ('%.8E' % Decimal(line[3]*mul)).rjust(16) + \
                    ('%.8E' % Decimal(line[4]*mul)).rjust(16) + \
                    ('%.8E' % Decimal(line[5]*mul)).rjust(16) + \
                    ('%.8E' % Decimal(line[6]*mul)).rjust(16) + \
                    ('%.8E' % Decimal(line[7]*mul)).rjust(16) + \
                    ('%.8E' % Decimal(line[8]*mul)).rjust(16) + '\n'

            f.write(coord + polar)

    f.close()

# %%
if os.path.exists(path + '/' + 'energy_out.dat'):

    df = pfEnergy_to_df(path + '/' +'energy_out.dat')

    plt.figure(figsize=(20, 9))
    plt.rc('xtick', labelsize=14)
    plt.rc('ytick', labelsize=14)

    df.loc[:,['Elastic_Energy', 'Electric_Energy', 'Landau_Energy',
           'OT+Coup_Energy', 'Grad_P_Energy', 'GradOT_Energy', 'Total_Energy']].plot()


    legend = plt.legend(frameon=False, loc = "upper right")

    plt.xlabel('step', fontsize=16)
    plt.ylabel('energy', fontsize=16)
    plt.tight_layout()

    for label in legend.get_texts():
        label.set_fontsize(14)

    for label in legend.get_lines():
        label.set_linewidth(3)  


    plt.savefig(path + '/energy.png', dpi=300,  transparent=True)

# %% [markdown]
# # Loop over Polar and Make .gif

# %%
for file in sorted(glob.glob(path + '/Polar*.dat')):
    plotDomains(file, 1e-4, 12, (12, 32))

# %%
png_dir = path + '/Polar_png/'
images = []
for file_name in [file for file in sorted(os.listdir(png_dir)) if '_' not in file]:
    if file_name.endswith('.png'):
        file_path = os.path.join(png_dir, file_name)
        images.append(imageio.imread(file_path))
imageio.mimsave(png_dir + png_dir.split('/')[-2] + '.gif', images, duration=0.25)

# %% [markdown]
# # Plot the last 3x3

# %%
plt.figure(figsize=(18, 18))
for p in range(9):
    plt.subplot(3, 3, p+1)
    plt.pcolormesh(dfp[:,:,p+12].T, cmap =cmap, norm=norm, vmin = -1, vmax = 26)
    plt.rc('xtick', labelsize=18)
    plt.rc('ytick', labelsize=18)
    plt.title('polar domain' + ' layer #{} (first 12)'.format(p+12), fontsize = 12)

#    for i in range(10): get_anno(dfp, 'p'); 

    plt.xlabel('X site', fontsize=18)
    plt.ylabel('Y site', fontsize=18)

plt.tight_layout()
plt.savefig(path + '/POLAR_9.png', dpi=300,  transparent=True)

# %%
plt.figure(figsize=(14, 5))
#plt.subplot(121)
plt.pcolormesh(dfp[:,0,:].T, cmap =cmap, norm=norm)
plt.rc('xtick', labelsize=18)
plt.rc('ytick', labelsize=18)
plt.title('polar domain', fontsize = 24)

cb = plt.colorbar(ticks = [ 0.2,  1,  2,  3,  4,  5,  6,  7,  8,  9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 25.8])
cb.ax.set_yticklabels(domainTypeLabel, fontsize = 12)


plt.xlabel('X site', fontsize=18)
plt.ylabel('Z site', fontsize=18)

plt.tight_layout()
plt.savefig(path + '/Polar_Y_slice.png', dpi=300,  transparent=True)

# %%
plt.figure(figsize=(12, 5))
plt.pcolormesh(dfp[60,:,:].T, cmap =cmap, norm=norm)
plt.rc('xtick', labelsize=18)
plt.rc('ytick', labelsize=18)
plt.title('polar domain', fontsize = 24)

cb = plt.colorbar(ticks = [ 0.2,  1,  2,  3,  4,  5,  6,  7,  8,  9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 25.8])
cb.ax.set_yticklabels(domainTypeLabel, fontsize = 12)

plt.xlabel('Y site', fontsize=18)
plt.ylabel('Z site', fontsize=18)

plt.tight_layout()
plt.savefig(path + '/Polar_X_slice.png', dpi=300,  transparent=True)

# %% [markdown]
# # plot.ly interactive (polar)

# %%
layer = 12
result = map(toDomain, dfp[:,:,layer].T.reshape(-1)) 
domains = np.array(list(result)).reshape(dfp[:,:,layer].shape[0], dfp[:,:,layer].shape[1])


fig = go.Figure(data =
      go.Heatmap(
        z=dfp[:,:,layer].T, 
        hovertext=domains,
          zmin = -1, zmax = 26,
        colorscale=paiColor,
      ), 
      layout = go.Layout(yaxis=dict(scaleanchor="x", scaleratio=1), 
                       height=800,
                       width=800, 
#                       paper_bgcolor='rgba(0, 0, 0, 0)', 
                       margin=go.layout.Margin(l=100, r=100, b=100, t=100, pad=2,)))
fig.update_layout(template="plotly_dark")
fig.show()

# %%
import plotly.graph_objects as go
from plotly.subplots import make_subplots
#dfp[dfp<0] = np.nan

fig = make_subplots(rows=2, cols=2, column_widths=[0.2, 0.8], row_heights = [0.2, 0.8])

layer = 12
result = map(toDomain, dfp[:,:,layer].T.reshape(-1)) 
domains = np.array(list(result)).reshape(dfp[:,:,layer].shape[0], dfp[:,:,layer].shape[1])
fig.add_trace(go.Heatmap(z=dfp[:,:,layer].T, zmin = -1, zmax = 26, hovertext=domains, colorscale=paiColor,), row=2, col=2)

fig.update_layout(go.Layout(yaxis=dict(scaleanchor="x", scaleratio=1), height=900, width=900, 
#                            paper_bgcolor='rgba(0, 0, 0, 0)', 
                            margin=go.layout.Margin(l=100, r=100, b=100, t=100, pad=2,)))
xcut = 60
result = map(toDomain, dfp[xcut,:,:].T.reshape(-1)) 
domains = np.array(list(result)).reshape(dfp[xcut,:,:].shape[1], dfp[xcut,:,:].shape[0]).T
fig.add_trace(go.Heatmap(z=dfp[xcut,:,:], zmin = -1, zmax = 26, hovertext=domains, colorscale=paiColor,), row=2, col=1)

ycut = 60
result = map(toDomain, dfp[:,ycut,:].reshape(-1)) 

domains = np.array(list(result)).reshape(dfp[:,ycut,:].shape[0], dfp[:,ycut,:].shape[1]).T
fig.add_trace(go.Heatmap(z=dfp[:,ycut,:].T, zmin = -1, zmax = 26, hovertext=domains, colorscale=paiColor,), row=1, col=2)
fig.update_layout(template="plotly_dark")
fig.show()

# %% [markdown]
# # plot.ly 3D interactive (polar)

# %%
'''
dfp_pd = dat_to_df(dfp[:, :, 11:18], list('xyz'))
domain3D = dfp_pd['A'].apply(lambda x: toDomain(x))

#plotly express code: 
#fig = px.scatter_3d(dfp_pd, x='x', y='y', z='z', color='A', opacity=0.2, )
#fig.update_traces(marker=dict(size=5, colorscale="Cividis", symbol = 'square'))
#fig.update_layout(margin=dict(l=0, r=0, b=0, t=0))
#fig.show()

fig = go.Figure(data=[go.Scatter3d(
    x=dfp_pd.x, y=dfp_pd.y, z=dfp_pd.z,
    mode='markers',
    hovertext=domain3D,
    marker=dict(
        size=4,
        color=dfp_pd.A,                # set color to an array/list of desired values
        colorscale=paiColor,   # choose a colorscale
        opacity=1,
    )
)])

# tight layout
fig.update_layout(margin=dict(l=0, r=0, b=0, t=0))
fig.show()
'''

# %% [markdown]
# # plot.ly interactive layer by layer (polar)

# %%
fig = go.Figure()
# Add traces, one for each slider step
for step in np.arange(12, 32, 1):
    fig.add_trace(
        go.Heatmap(
            z=dfp[:,:,step].T,
            zmin = -1, zmax = 26, 
            visible=False, colorscale=paiColor, 
            hovertext=np.array(list(map(toDomain, dfp[:,:,step].\
                                        T.reshape(-1)))).reshape(dfp[:,:,step].shape[0], dfp[:,:,step].shape[1]),
            name="o " + str(step),))
    
fig.update_layout(go.Layout(yaxis=dict(scaleanchor="x", scaleratio=1), height=700, width=700, 
#                            paper_bgcolor='rgba(0, 0, 0, 0)', 
                            margin=go.layout.Margin(l=100, r=100, b=100, t=100, pad=0,)))

# Make 10th trace visible
fig.data[0].visible = True

# Create and add slider
steps = []
for i in range(len(fig.data)):
    step = dict(
        method="restyle",
        args=["visible", [False] * len(fig.data)],
    )
    step["args"][1][i] = True  # Toggle i'th trace to "visible"
    steps.append(step)

sliders = [dict(
    active=0,
    currentvalue={"prefix": "layer: "},
    pad={"t": 50},
    steps=steps,
    ticklen = 0
)]

fig.update_layout(
    sliders=sliders
)

fig.update_layout(template="plotly_dark")
#fig.update_layout(margin=dict(l=0, r=0, b=0, t=0))
fig.show()



# %% [markdown]
# # Read last OctaTilt 

# %%
%%time
fileInstance = sorted(glob.glob(path + '/OctaTilt*.dat'))[-1]
dfo = plotDomains(fileInstance, 1e-12, 12, (12, 32))

# %%
path

# %% [markdown]
# # Loop over OctaTilt and make gif

# %%
%%time
path = hello.value; print(path)

for file in sorted(glob.glob(path + '/OctaTilt*.dat')):
    plotDomains(file, 1e-12, 12, (12, 32))

# %%
png_dir = path + '/OctaTilt_png/'
images = []
for file_name in [file for file in sorted(os.listdir(png_dir)) if '_' not in file]:
    if file_name.endswith('.png'):
        file_path = os.path.join(png_dir, file_name)
        images.append(imageio.imread(file_path))
imageio.mimsave(png_dir + png_dir.split('/')[-2] + '.gif', images, duration=0.25)

# %% [markdown]
# # Octatilt slice

# %%
plt.figure(figsize=(13, 5))
#plt.subplot(121)
plt.pcolormesh(dfo[:,0,:].T, cmap =cmap, norm=norm)
plt.rc('xtick', labelsize=18)
plt.rc('ytick', labelsize=18)
plt.title('polar domain', fontsize = 24)

cb = plt.colorbar(ticks = [ 0.2,  1,  2,  3,  4,  5,  6,  7,  8,  9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 25.8])
cb.ax.set_yticklabels(domainTypeLabel, fontsize = 12)

plt.xlabel('X site', fontsize=18)
plt.ylabel('Z site', fontsize=18)


plt.tight_layout()
plt.savefig(path + '/OCTA_Y_slice.png', dpi=300,  transparent=True)

# %% [markdown]
# # 3x3 

# %%
plt.figure(figsize=(18, 18))

for p in range(9):
    plt.subplot(3, 3, p+1)
    plt.pcolormesh(dfo[:,:,p+12].T, cmap =cmap, norm=norm)
    plt.rc('xtick', labelsize=18)
    plt.rc('ytick', labelsize=18)
    plt.title('octa domain' + ' layer #{} (first 12)'.format(p+12), fontsize = 12)

#    for i in range(10): get_anno(dfo, 'o'); 

    plt.xlabel('X site', fontsize=18)
    plt.ylabel('Y site', fontsize=18)
    
plt.tight_layout()
plt.savefig(path + '/OCTA_9.png', dpi=300,  transparent=True)

# %%


# %% [markdown]
# # Plotly with slice

# %%
fig = make_subplots(rows=3, cols=2, column_widths=[0.2, 0.8], row_heights = [0.2, 0.8, 0.1])

layer = 12
result = map(toDomain, dfo[:,:,layer].T.reshape(-1)) 
domains = np.array(list(result)).reshape(dfo[:,:,layer].shape[0], dfo[:,:,layer].shape[1])
fig.add_trace(go.Heatmap(z=dfo[:,:,layer].T, zmin = -1, zmax = 26, hovertext=domains, colorscale=paiColor,), row=2, col=2)

fig.update_layout(go.Layout(yaxis=dict(scaleanchor="x", scaleratio=1), height=800, width=700, 
#                            paper_bgcolor='rgba(0, 0, 0, 0)', 
                            margin=go.layout.Margin(l=100, r=100, b=100, t=100, pad=2,)))


xcut = 60
result = map(toDomain, dfo[xcut,:,:].T.reshape(-1)) 
domains = np.array(list(result)).reshape(dfo[xcut,:,:].shape[1], dfo[xcut,:,:].shape[0]).T
fig.add_trace(go.Heatmap(z=dfo[xcut,:,:], zmin = -1, zmax = 26, hovertext=domains, colorscale=paiColor,), row=2, col=1)


ycut = 60
result = map(toDomain, dfo[:,ycut,:].reshape(-1)) 
domains = np.array(list(result)).reshape(dfo[:,ycut,:].shape[0], dfo[:,ycut,:].shape[1]).T
fig.add_trace(go.Heatmap(z=dfo[:,ycut,:].T, zmin = -1, zmax = 26, hovertext=domains, colorscale=paiColor,), row=1, col=2)


values = np.vstack([np.arange(0, 27, 1), np.arange(0, 27, 1)])
result = map(toDomain, values.reshape(-1)) 
domains = np.array(list(result)).reshape(values.shape[0],values.shape[1])
fig.add_trace(go.Heatmap(z=np.vstack([np.arange(0, 27, 1), np.arange(0, 27, 1)]), 
                         zmin = -1, zmax = 26, hovertext=domains, colorscale=paiColor,), row=3, col=2)


fig.update_layout(template="plotly_dark")
fig.show()

# %%
fig = go.Figure()
# Add traces, one for each slider step
for step in np.arange(12, 32, 1):
    fig.add_trace(
        go.Heatmap(
            z=dfo[:,:,step].T,
            zmin = -1, zmax = 26,
            visible=False, colorscale=paiColor, 
            hovertext=np.array(list(map(toDomain, dfo[:,:,step].\
                                        T.reshape(-1)))).reshape(dfo[:,:,step].shape[0], dfo[:,:,step].shape[1]),
            name="o " + str(step),))
    
fig.update_layout(go.Layout(yaxis=dict(scaleanchor="x", scaleratio=1), height=700, width=700, 
#                            paper_bgcolor='rgba(0, 0, 0, 0)', 
                            margin=go.layout.Margin(l=100, r=100, b=100, t=100, pad=0,)))

# Make 10th trace visible
fig.data[0].visible = True

# Create and add slider
steps = []
for i in range(len(fig.data)):
    step = dict(
        method="restyle",
        args=["visible", [False] * len(fig.data)],
    )
    step["args"][1][i] = True  # Toggle i'th trace to "visible"
    steps.append(step)

sliders = [dict(
    active=0,
    currentvalue={"prefix": "layer: "},
    pad={"t": 50},
    steps=steps,
    ticklen = 0
)]

fig.update_layout(
    sliders=sliders
)

fig.update_layout(template="plotly_dark")
#fig.update_layout(margin=dict(l=0, r=0, b=0, t=0))
fig.show()

# %%
# Plotly both

# %%
fig = make_subplots(rows=1, cols=2, subplot_titles=("Polar", "Octa",))

layer = 12

result = map(toDomain, dfp[:,:,layer].T.reshape(-1)) 
domains = np.array(list(result)).reshape(dfp[:,:,layer].shape[0], dfp[:,:,layer].shape[1])
fig.add_trace(go.Heatmap(z=dfp[:,:,layer].T, zmin = -1, zmax = 26, hovertext=domains, colorscale=paiColor,), row=1, col=1)


result = map(toDomain, dfo[:,:,layer].T.reshape(-1)) 
domains = np.array(list(result)).reshape(dfo[:,:,layer].shape[0], dfo[:,:,layer].shape[1])
fig.add_trace(go.Heatmap(z=dfo[:,:,layer].T, zmin = -1, zmax = 26, hovertext=domains, colorscale=paiColor,), row=1, col=2)

fig.update_layout(height=600, width=1100, title_text="Layer 12")
fig.update_layout(template="plotly_dark")
fig.show()

# %%
dfo_pd = dat_to_df(dfo[:, :, 11:25], list('xyz'))
domain3D = dfo_pd['A'].apply(lambda x: toDomain(x))


fig = go.Figure(data=[go.Scatter3d(
    x=dfo_pd.x,
    y=dfo_pd.y,
    z=dfo_pd.z,
    mode='markers',
    hovertext=domain3D,
    marker=dict(
        size=1,
        color=dfo_pd.A,                # set color to an array/list of desired values
        colorscale=paiColor,   # choose a colorscale
        opacity=0.6,
    )
)])

# tight layout

fig.update_layout(scene_aspectmode='manual',
                  scene_aspectratio=dict(x=1, y=1, z=0.1))

fig.update_layout(margin=dict(l=0, r=0, b=0, t=0))
fig.update_layout(template="plotly_dark")
fig.show()

# %%
#dfo_pd = dat_to_df(dfo[:, :, 12:20], list('xyz'))
#domain3D = dfo_pd['A'].apply(lambda x: toDomain(x))
#dfo_pd.to_csv('OctaTilt.domain', index = False)

# %%
'''
%%time
list_file = sorted(glob.glob(path + '/OctaTilt*.dat'))
fig = go.Figure()
# Add traces, one for each slider step
for step in np.arange(0, len(list_file), 1):
    df = readDatFerroDomain(list_file[step], threshO, 90)
    fig.add_trace(
        go.Heatmap(
            z=df[:,:,12].T, 
            zmin = -1, zmax = 26,
            visible=False, colorscale=paiColor, 
            hovertext=np.array(list(map(toDomain, df[:,:,12].\
                                        T.reshape(-1)))).reshape(df[:,:,12].shape[0], df[:,:,12].shape[1]),
            name="o " + str(step),))
    
fig.update_layout(go.Layout(yaxis=dict(scaleanchor="x", scaleratio=1), height=700, width=700, 
                            paper_bgcolor='rgba(0, 0, 0, 0)', 
                            margin=go.layout.Margin(l=100, r=100, b=100, t=100, pad=0,)))

# Make 10th trace visible
fig.data[0].visible = True

# Create and add slider
steps = []
for i in range(len(fig.data)):
    step = dict(
        method="restyle",
        args=["visible", [False] * len(fig.data)],
    )
    step["args"][1][i] = True  # Toggle i'th trace to "visible"
    steps.append(step)

sliders = [dict(
    active=0,
    currentvalue={"prefix": "layer: "},
    pad={"t": 50},
    steps=steps,
    ticklen = 0
)]

fig.update_layout(
    sliders=sliders
)
#fig.update_layout(margin=dict(l=0, r=0, b=0, t=0))
fig.show()
'''

# %%


# %%


# %%
