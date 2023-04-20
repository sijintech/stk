# -*- coding: utf-8 -*-
"""
Created on Mon Feb 18 11:40:52 2019

@author: cxx

This is the general header file for all research data processing and plotting
"""
import numpy as np
import pandas as pd
import re
import glob
import os
import sys
import matplotlib.pyplot as plt
# import svgutils.transform as sg
#import muproData.svg_stack as ss
#import muproData.svg_stack as ss
import datetime

#%%    

def touch(folder):
    if not os.path.exists(folder):
        print("Creating ",folder)
        os.makedirs(folder)
    else:
        print(folder,' already exist')
        
def touchFile(file):
    if not os.path.exists(file):
        print("Creating ",file)
        with open(file,'w') as f:
            f.write('File created on '+str(datetime.datetime.now()))
    else:
        print(file,' already exist')

def regular_expression(regex,string,flags=0):
    return re.compile(regex,flags).findall(string)

def merge_dict(baseDict,newDict):
    for key in newDict:
        if key in baseDict:
            if type(baseDict[key]) == set:
                baseDict[key]=baseDict[key]|newDict[key]
            elif type(baseDict[key]) == dict:
                baseDict[key]=dict(**baseDict[key],**newDict[key])
            elif type(baseDict[key]) == list:
                baseDict[key]=baseDict[key]+newDict[key]
            else:
                print('Neither list nor dict', key,baseDict[key])
        else:
            baseDict[key]=newDict[key]
    return baseDict

def dict_expand(dictionary,key,value):
    outDict = dictionary
    if key in dictionary:
        outDict = merge_dict(dictionary,{key:value})
    else:
        outDict[key] = value
    return outDict

def get_file_list(path='.',wildCard='.+'):
    f = []
    for (dirpath, dirnames, filenames) in os.walk(path):
        for filename in filenames:
            # print(filename)
            if len(regular_expression(wildCard,str(filename)))>0:
                f.append(filename)
        break
    return f

def get_file_list_by_extension(path='.'):
    files = get_file_list(path)
    outDict = {}
    for file in files:
        fileNameSeparated = file.split(os.path.extsep)
        extension = fileNameSeparated[-1]
        outDict = dict_expand(outDict,extension,[file])
    return outDict

def get_file_list_by_timeStep(path='.'):
    files = get_file_list(path)
    outDict = {}
    for file in files:
        timeStep = regular_expression(r'\.(\d{8})\.',file)

        if len(timeStep) > 0:
            outDict = dict_expand(outDict,int(timeStep[0]),[file])
    return outDict

def get_file_list_by_purpose(path='.'):
    files = get_file_list(path)
    outDict = {}
    for file in files:
        fileNameSeparated = file.split(os.path.extsep)
        purpose = fileNameSeparated[0]
        outDict = dict_expand(outDict,purpose,[file])
    return outDict

def string_list_to_dict(stringList,sep=os.path.extsep,direction='F'):
    outDict = {}
    for string in stringList:
        stringSeparated = string.split(sep)
        first = stringSeparated[0] if direction=='F' else stringSeparated[-1]
        remain = sep.join(stringSeparated[1:]) if direction=='F' else sep.join(stringSeparated[:-1])
        if len(stringSeparated) > 2:
            outDict = dict_expand(outDict,first,[remain])
        elif len(stringSeparated) == 2:
            outDict[first] = remain
        elif len(stringSeparated) == 1:
            outDict = dict_expand(outDict,'root',first)
        else:
            print("You have an empty string in ",stringList)
            break
    
    for k in outDict:
        if type(outDict[k]) == list:
            outDict[k] = string_list_to_dict(outDict[k],sep,direction)
    return outDict

def dict_key_addup(dictionary,sep=os.path.extsep,passOn='',direction='F'):
    outDict = {}
    outDict = dictionary
    if passOn=='':
        passOnVal=''
    else:
        passOnVal=passOn + sep if direction == 'F' else sep + passOn

    for k in dictionary:
        if type(dictionary[k]) == dict:
            if direction == 'F':
                outDict[k] = dict_key_addup(dictionary[k],sep,passOnVal+k,direction) 
            else: 
                outDict[k] = dict_key_addup(dictionary[k],sep,k + passOnVal,direction) 
        elif type(dictionary[k]) == list:
            outDict[k] = []
            for anything in dictionary[k]:
                if direction == 'F':
                    outDict[k].append(passOnVal + k + sep + anything)
                else:
                    outDict[k].append(anything + sep + k + passOnVal)
        elif type(dictionary[k]) == str:
            if direction == 'F':
                outDict[k] = passOnVal + k + sep + dictionary[k]
            else:
                outDict[k] = dictionary[k] + sep + k + passOnVal
    return outDict
    
def get_file_tree_forward(path='.'):
    files = get_file_list(path)
    outDict = {}
    outDict = string_list_to_dict(files,sep=os.path.extsep,direction='F')
    outDict = dict_key_addup(outDict,sep=os.path.extsep,passOn='',direction='F')
    return outDict

def get_file_tree_reverse(path='.'):
    files = get_file_list(path)
    outDict = {}
    outDict = string_list_to_dict(files,sep=os.path.extsep,direction='B')
    outDict = dict_key_addup(outDict,sep=os.path.extsep,passOn='',direction='B')
    return outDict

def get_folder_list(path='.'):
    # folders = glob.glob(folder+'/*/')
    # return [a.split(os.path.sep)[1] for a in folders]
    f = []
    for (dirpath, dirnames, filenames) in os.walk(path):
        f.extend(dirnames)
        break
    return f
    
def get_batch_folder_list(folder='.'):
    folderList = get_folder_list(folder)
    out_folder = []
    for i in range(0,len(folderList)):
        first=regular_expression(r'\d*',folderList[i])[0]
        if first != '':
            out_folder.append(folderList[i])
    return out_folder
    
def recognize_value(string,sep='_'):
    out=string.split(sep)
    if len(out)==1:
        return out[0]
    else:
        return out
    
def parse_folder_name(folderName):
    if os.path.isdir(folderName):
        print(folderName," is a path")
        folderName = os.path.dirname(folderName+os.path.sep)
        folderName = folderName.split(os.path.sep)[-1]
    indexLabel = regular_expression(r'^\d+(?=\+)',folderName)[0]
    values= regular_expression(r"\+([^\_]+)\_([^\+]+)",folderName)
    valuesDict = {a[0]:recognize_value(a[1]) for a in values}
    return valuesDict,indexLabel

def parse_string_for_variable(string):
    values= regular_expression(r"([^=\_\/]*)=([^_]*)",string)
    valuesDict = {a[0]:a[1] for a in values}
    return valuesDict

def get_energy(folderName):
    
    return energy
    
def prepare_2D_data(filename):
    
    return data2D

def readTimeData(name,indexList):
    file=open(name)
    lines=file.readlines()
    e=np.zeros((len(indexList),3))
    for index in indexList:
        ind=indexList.index(index)
        values=lines[index+1].rstrip().split()
        time=values[0]
        e[ind,0] = values[1]
        e[ind,1] = values[2]
        e[ind,2] = values[3]
    file.close()
    return e

def print_heatPlot(withConfig=True):
    if withConfig:
        text='''
r=config['range']
plt.imshow(data.T[r[2]:r[3],r[0]:r[1]],origin='lower',extent=[r[0],r[1],r[2],r[3]])
plt.colorbar()
plt.axis('off')
plt.savefig(file)
plt.show()
plt.close()
        '''
    else:
        text='''
plt.imshow(data.T,origin='lower')
plt.colorbar()
plt.axis('off')
plt.savefig(file)
plt.show()
plt.close()
        '''
    print(text)

def get_val_list(imgNames=get_file_list('.')):
    keys=set()
    vals={}
    for name in imgNames:
        name_dict=parse_string_for_variable(name)
        keys=keys|name_dict.keys()

    if len(keys)>2:
        print('more then two keywords, currently we only support 2D mapping')
    else:
        print("The keywords are, ",keys)
    for key in keys:
        vals[key]=set()
        for name in imgNames:
            name_dict=parse_string_for_variable(name)
            vals[key]=vals[key]|{name_dict[key]}
        vals[key] = list(vals[key])
    return keys,vals




def convertDictTo2D(data_dict):
    position=list(data_dict.keys())
    listX=set()
    listY=set()
    for posX,posY in position:
        listX=listX|{float(posX)}
        listY=listY|{float(posY)}
    sortX = sorted(list(listX))
    sortY = sorted(list(listY))
    out_data = np.zeros((len(listX),len(listY)))
    for x in sortX:
        for y in sortY:
            indexX = sortX.index(x)
            indexY = sortY.index(y)
            out_data[indexX][indexY] = data_dict[(x,y)]
    return out_data



def plotLine(dataName):
    fileName=os.path.basename(dataName)
    dirName=os.path.dirname(dataName)
    figTitle = dirName
    figName = '_'.join(dirName.split(os.path.sep))
    
    range = params['range']
    xlimRange = params['xlimRange']
    figTitleZ = figTitle + ' pz'
    figNameZ = figName + '-pz.png'
    figTitleX = figTitle + ' px'
    figNameX = figName + '-px.png'
    figTitleLine = figTitle + ' profile along z'
    figNameLine = figName + '-line.png'
    
    data = muproData.readDat.readDatScalar(dataName)
    polar = data[:,:,:,0:3]
    nx=np.shape(polar)[0]
    nz=np.shape(polar)[2]
    xgrid = np.linspace(1,nx,nx)
    ygrid = np.linspace(1,nz,nz)
    x,y = np.meshgrid(xgrid,ygrid)
    px = polar[:,0,:,0]
    pz = polar[:,0,:,2]
    
    
    plt.figure()
    #plt.quiver(x,y,px.transpose(),pz.transpose(),scale=2)
    plt.xlim(xlimRange[0],xlimRange[1])
    plt.ylim(range[0],range[1])
    plt.plot(ygrid,pz[int(nx/2),:],label='pz')
    plt.plot(ygrid,px[int(nx/2),:],label='px')
    plt.legend()
    plt.title(figTitleLine)
    plt.savefig(params['imgPath']+figNameLine,dpi=200)
    plt.show()

def researchInit(root='.'):
    touch(root+'/img')
    touch(root+'/img/paper')
    touch(root+'/img/general')    
    touch(root+'/img/visual')
    
    touch(root+'/data')
    touch(root+'/data/raw')
    touch(root+'/data/processed')
    
    touch(root+'/code')
    
    touch(root+'/paper')
    
    touch(root+'/note')
    touch(root+'/note/slide')
    touch(root+'/note/doc')
    
    touch(root+'/vuepress')
    
    touchFile(root+'/README.md')
    string='''
# Setup the git repository
In the code directory
```
git init
git add --all
git commit -m "Initial commit"
git remote add origin git@gitlab.com:chengxiaoxing/YOUR_REMOTE_REPO.git
git push -u origin master
```
# The vuepress page
When the figures are ready, you can setup the vuepress page using template at 
```
git clone git@gitlab.com:chengxiaoxing/vuepress-manuscript-template.git
```
# Dependency
You need the other data processing api muproData for easier usage
```
git clone git@gitlab.com:lqc-group/mupro-data-api.git
```
# List of figures
1. Figure 1:
2. Figure 2:
    '''
    with open('README.md','a') as file:
        file.write(string)
    
