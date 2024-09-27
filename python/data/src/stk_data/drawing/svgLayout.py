from svgutils.transform import SVGFigure
import svgutils.transform as svgtrans
import copy
from lxml import etree
import base64
import PIL.Image
import svgutils.transform as sg
from math import ceil
import cairosvg
import os
import muproData.svg_stack as ss
from ..research.research_header import *

def svg_grid(outFileName,imgNames=get_file_list('.'),vals_in={}):
   
    keys,vals=get_val_list(imgNames)
    if len(vals_in)!=0:
        vals = vals_in 

    # determine which dimension is longer
    keyList=list(keys)
    dimension=[keyList[0]]
    if len(keys)==2:
        if len(vals[keyList[0]]) > len(vals[keyList[1]]):
            dimension.append(keyList[1])
        else:
            dimension=[keyList[1]]+dimension

    grid_dict={}
    for name in imgNames:
        name_dict=parse_string_for_variable(name)
        x = vals[dimension[0]].index(name_dict[dimension[0]])
        y = vals[dimension[1]].index(name_dict[dimension[1]])
        grid_dict[(x,y)] = name


    doc = ss.Document()
    layoutAll = ss.VBoxLayout()

    layoutHBox = []
    for y in range(0,len(vals[dimension[1]])):
        layoutHNew = ss.HBoxLayout()
        for x in range(0,len(vals[dimension[0]])):
            imgNames = grid_dict[(x,y)]
            layoutHNew.addSVG(imgNames)
        layoutHBox.append(layoutHNew)
        layoutAll.addLayout(layoutHBox[y])
        
    doc.setLayout(layoutAll)

    buf = doc.save()
    #Add label to the image

    # fig = sg.fromfile('../test.svg')
    fig = sg.fromstring(buf)
    size = fig.get_size()
    one_size = [float(size[0])/len(vals[dimension[0]]),float(size[1])/len(vals[dimension[1]])]
    new_size = [float(size[0])+1000,float(size[1])+1000]
    figNew = sg.SVGFigure(str(new_size[0]),str(new_size[1]) )
    plot1 = fig.getroot()

    height = 50

    txt_col=[]
    for x in range(0,len(vals[dimension[0]])):
        txt1 = sg.TextElement(x*one_size[0]+0.5*one_size[0],float(size[1])+height,dimension[0]+'='+vals[dimension[0]][x], size=30, weight="bold",anchor='middle')
        txt_col.append(txt1)
    txt_row=[]
    for y in range(0,len(vals[dimension[1]])):
        txt2 = sg.TextElement(height, y*one_size[1]+0.5*one_size[1],dimension[1]+'='+vals[dimension[1]][y], size=30, weight="bold",anchor='middle')
        txt2.rotate(-90,height,y*one_size[1]+0.5*one_size[1])
        txt_row.append(txt2)
    figNew.append([plot1]+txt_col+txt_row)
    figNew.save(outFileName)
    
    
    
# the following is from the svg_utils/transform for the clearFigure purpose
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
XLINK_NAMESPACE = "http://www.w3.org/1999/xlink"
SVG = "{%s}" % SVG_NAMESPACE
XLINK = "{%s}" % XLINK_NAMESPACE
NSMAP = {None: SVG_NAMESPACE,
         'xlink': XLINK_NAMESPACE}

class svgLayout(SVGFigure):
    """
    For setting the whole svg image size and layout
    possible configuration parameters are:

    """
    def __init__(self, config=None):
        SVGFigure.__init__(self)
        self.figures = []
        self.labeledFigures = []
        self.figPosition = []
        self.configuration = []
        config_hold = self.getDefaultConfig()
        if config:
            self.setConfig(config)
        else:
            self.setConfig(config_hold)
    
    def clearFigure(self):
        self.root = etree.Element(SVG+"svg", nsmap=NSMAP)
        self.root.set("version", "1.1")

    def deepClean(self, config=None):
        self.clearFigure()
        self.figures = []
        self.labeledFigures = []
        self.figPosition = []
        self.configuration = []
        config_hold = self.getDefaultConfig()
        if config:
            self.setConfig(config)
        else:
            self.setConfig(config_hold)

    def setConfig(self,config):
        self.configuration = config

    def getConfig(self):
        # return copy.deepcopy(self.configuration)
        return self.configuration

    def getPosition(self):
        return self.figPosition
    
    def setPosition(self,position):
        self.figPosition = position

    def getDefaultConfig(self):
        config={}
        config.update({'width': 500})
        config.update({'height': 300})
        config.update({'layout': "rowcol"})
        config.update({'rowNum':0})
        config.update({'colNum':0})
        config.update({'rowHeight': 0})
        config.update({'colWidth': 0})
        config.update({'position': 'auto'})
        config.update({'sizePolicy': 'original'})
        config.update({'fileName': "default.svg"})
        config.update({'showLabel':True})
        config.update({'labelSize': 30})
        config.update({'labelWeight': 'Bold'})
        config.update({'labelColor': 'Black'})
        config.update({'label': []})
        return copy.deepcopy(config)

    def printDefaultConfig(self):
        formatString="%30s : %s"
        print( formatString % ('width', 'string'))
        print( formatString % ('height', 'string'))
        print( formatString % ('layout ',' string [rowcol,colrow]'))
        print( formatString % ('position ',' string [manual,auto]'))
        print( formatString % ('sizePolicy ',' string [original,fix,fixWidth,fixHeight]'))
        print( formatString % ('filename ', 'string'))

    def _addLetterLabel(self,mask=None):
        textSize = self.configuration['labelSize']
        textSizePixel = textSize*1.2
        textWeight = self.configuration['labelWeight']
        textColor = self.configuration['labelColor']
        for i in range(0,len(self.figures)):
            posX=self.figPosition[i][0]
            posY=self.figPosition[i][1]
            points = [[posX,posY+textSizePixel/2.0],[posX+textSizePixel,posY+textSizePixel/2.0]]
            txtbg = svgtrans.LineElement(points,width=textSizePixel,color='White')
            text = self.configuration['label'][i]
            txt =svgtrans.TextElement(posX+textSizePixel/2,posY+textSizePixel*5/6,text,size=textSize,weight=textWeight,color=textColor,anchor='middle')
            # self.labeledFigures[i] = copy.deepcopy(self.figures[i])
            self.labeledFigures[i].append([txtbg,txt])

    def addPNGFigureFromFile(self,filename):
        imageFile = open(filename,'rb')
        im = PIL.Image.open(filename)
        w,h = im.size
        pngImage=svgtrans.ImageElement(imageFile,w,h)
        outSVG = SVGFigure(w,h)
        outSVG.append(pngImage)
        self.addFigure(outSVG)
        imageFile.close()

    def addFigureFromFile(self,filename):
        fig = sg.fromfile(filename)
        self.addFigure(fig)

    def addFigure(self,fig):
        w, h = fig.get_size()
        # if w == None or h == None:
        #     fig.save('temp.svg')
        #     cairosvg.svg2png(url='temp.svg',write_to='temp.png')
        #     im = PIL.Image.open('temp.png')
        #     w,h = im.size
        #     os.remove('temp.svg')
        #     os.remove('temp.png')
        #     fig.width = w
        #     fig.height = h
            
        # print("size %i %i" % (w,h))
        # root = fig.getroot()
        # self.figures.append({'root': root,'width':w,'height':h})
        # self.labeledFigures.append({'root': root,'width':w,'height':h})
        # fig.save('./img/fig1.svg') 
        self.figures.append(fig)
        self.labeledFigures.append(fig)
        self.figPosition.append([0,0,1.0])
        self.configuration['label'].append(chr(64+len(self.figures)))
        # self.figures[0].save('./img/fig2.svg')
        # self.labeledFigures[0].save('./img/fig3.svg')

    def _addFigureList(self,figs):
        for fig in figs:
            self._addFigure(fig)

    def _addFigure(self,fig):
        """
        The fig is a SVGFigure object, this is the real append which added
        the fig into the current svg object. which different from the other 
        "addFigure" function which only add to the figure list, and waiting
        for further processing of the figure, such as rescaling and adding label
        """
        self.append(fig)

    def _updatePositionAuto(self):
        colNum = self.configuration['colNum']
        rowNum = self.configuration['rowNum']
        colWidth = self.configuration['colWidth']
        rowHeight = self.configuration['rowHeight']
        totalWidth = self.configuration['width']
        totalHeight = self.configuration['height']
        if self.configuration['layout'] == 'rowcol':
            if colNum<=0:
                colNum = len(self.figures)
                rowNum = 1
            else:
                rowNum = ceil(len(self.figures)/colNum)
        elif self.configuration['layout'] == 'colrow':
            if rowNum<=0:
                rowNum = len(self.figures)
                colNum = 1
            else:
                colNum = ceil(len(self.figures)/rowNum)

        markerX = 0
        markerY = 0
        previousRowHeight = 0
        previousColWidth = 0
        scaleFactor = 1.0
        figWidth = 0
        figHeight = 0
        for i in range(0,len(self.figures)):
            fig = self.figures[i]
            if self.configuration['layout']=='rowcol':
                col = i%colNum + 1
                row = ceil(i/colNum)
                if col == 1:
                    markerX = 0
                    markerY = markerY + previousRowHeight
                else:
                    markerX = markerX + previousColWidth
            elif self.configuration['layout']=='colrow':
                row = i%rowNum + 1
                col = ceil(i/rowNum)
                if row == 1:
                    markerY = 0
                    markerX = markerX + previousColWidth
                else:
                    markerY = markerY + previousRowHeight
            else:
                print("The layout setting is unrecognized, acceptable keywords are rowcol, colrow and auto.")

            if self.configuration['sizePolicy'] == 'original':
                print("Using the original size of image")
                scaleFactor = 1.0
                figWidth = int(fig.width)
                figHeight = int(fig.height)

            elif self.configuration['sizePolicy'] == 'fixWidth':
                if colWidth*colNum > totalWidth:
                    print('The total width is less than column width*column numbers, fixWidth case.')
                scaleFactor = colWidth/int(fig.width)
                figWidth = colWidth
                figHeight = int(fig.height)*scaleFactor
                if markerY + figHeight > totalHeight:
                    print('The total height is less than sum of row height, fixWidth case.')

            elif self.configuration['sizePolicy'] == 'fixHeight':
                if rowHeight*rowNum > totalHeight:
                    print('The total height is less than row height * row number, fixHeight case.')
                scaleFactor = rowHeight/int(fig.height)
                figHeight = rowHeight
                figWidth = int(fig.width)*scaleFactor
                if markerX+figWidth > totalWidth:
                    print('The total width is less than sum of all columns width, fixHeight case.')
            
            elif self.configuration['sizePolicy'] == 'fixed':
                if rowHeight*rowNum > totalHeight:
                    print('The total height is less than row height * row number, fixed case.')
                if colWidth*colNum > totalWidth:
                    print('The total width is less than column width*column numbers, fixed case.')
                figWidth = colWidth
                figHeight = rowHeight
                if rowHeight/int(fig.height) > colWidth/int(fig.width) :
                    scaleFactor = colWidth/int(fig.width)
                else:
                    scaleFactor = rowHeight/int(fig.height)
            
            if previousRowHeight < figHeight:
                previousRowHeight = figHeight  
            if previousColWidth < figWidth:
                previousColWidth = figWidth
            self.figPosition[i][0] = markerX
            self.figPosition[i][1] = markerY
            self.figPosition[i][2] = scaleFactor
            print("scaleFactor %f %f %f" % (markerX,markerY,scaleFactor))


    def _updateLayout(self):
        self.clearFigure()
        self.width = self.configuration['width']
        self.height = self.configuration['height']
        if self.configuration['position'] == 'auto':
            self._updatePositionAuto()
        elif self.configuration['position'] == 'manual':
            # self._updatePositionManual()
            a = 0 # doing nothing
        else:
            print('The position configuration is unknown, use auto or manual.')

        for i in range(0,len(self.figures)):
            print(i)
            posX=self.figPosition[i][0]
            posY=self.figPosition[i][1]
            scaleFactor = self.figPosition[i][2]
            # print(posX,posY)
            # self.labeledFigures[i].save('./img/addfigure1.svg')
            hold=self.labeledFigures[i].getroot()
            hold.moveto(posX,posY,scale=scaleFactor)
            self.labeledFigures[i].append(hold)
            # self.labeledFigures[i].save('./img/addfigure2.svg')

        if self.configuration['showLabel']:
            self._addLetterLabel()
        
        for i in range(0,len(self.figures)):
            self._addFigure(self.labeledFigures[i].getroot())


    def save(self,fname=None):
        self._updateLayout()
        if fname:
            SVGFigure.save(self,fname)
        else:
            SVGFigure.save(self,self.configuration['filename'])
