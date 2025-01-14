import numpy as np
import matplotlib as mpl

mpl.use('agg')
import matplotlib.pyplot as plt
from matplotlib import cm
# from colorspacious import cspace_converter
from collections import OrderedDict
from PIL import Image
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.patches as patches
import copy
import os

cmaps = OrderedDict()

# def plot_color_gradients(cmap_category, cmap_list):
# 	mpl.rcParams.update({'font.size': 14})
# 	# Indices to step through colormap.
# 	x = np.linspace(0.0, 1.0, 100)

# 	gradient = np.linspace(0, 1, 256)
# 	gradient = np.vstack((gradient, gradient))

# 	fig, axes = plt.subplots(nrows=len(cmap_list), ncols=1)
# 	fig.subplots_adjust(top=0.95, bottom=0.01, left=0.2, right=0.99,wspace=0.05)
# 	fig.suptitle(cmap_category + ' colormaps', fontsize=14, y=1.0, x=0.6)

# 	for ax, name in zip(axes, cmap_list):

# 	    # Get RGB values for colormap.
# 	    rgb = cm.get_cmap(plt.get_cmap(name))(x)[np.newaxis, :, :3]

# 	    # Get colormap in CAM02-UCS colorspace. We want the lightness.
# 	    lab = cspace_converter("sRGB1", "CAM02-UCS")(rgb)
# 	    L = lab[0, :, 0]
# 	    L = np.float32(np.vstack((L, L, L)))

# 	    ax[0].imshow(gradient, aspect='auto', cmap=plt.get_cmap(name))
# 	    ax[1].imshow(L, aspect='auto', cmap='binary_r', vmin=0., vmax=100.)
# 	    pos = list(ax[0].get_position().bounds)
# 	    x_text = pos[0] - 0.01
# 	    y_text = pos[1] + pos[3]/2.
# 	    fig.text(x_text, y_text, name, va='center', ha='right', fontsize=10)

# 	# Turn off *all* ticks & spines, not just the ones with colormaps.
# 	for ax in axes.flat:
# 	    ax.set_axis_off()

# 	plt.show()


def plot_color_gradients(cmap_category, cmap_list, nrows):
    gradient = np.linspace(0, 1, 256)
    gradient = np.vstack((gradient, gradient))
    fig, axes = plt.subplots(nrows=nrows, figsize=(3, 2), dpi=300)
    fig.subplots_adjust(top=0.85, bottom=0.01, left=0.3, right=0.99)
    axes[0].set_title(cmap_category + ' colormaps', fontsize=8)

    for ax, name in zip(axes, cmap_list):
        ax.imshow(gradient, aspect='auto', cmap=plt.get_cmap(name))
        pos = list(ax.get_position().bounds)
        x_text = pos[0] - 0.01
        y_text = pos[1] + pos[3] / 2.
        fig.text(x_text, y_text, name, va='center', ha='right', fontsize=6)

    # Turn off *all* ticks & spines, not just the ones with colormaps.
    for ax in axes:
        ax.set_axis_off()

    plt.close(fig)
    return fig


def concatImageCol(imga, imgb):
    """
	Combines two color image ndarrays side-by-side left to right.
	"""
    ha, wa = imga.shape[:2]
    hb, wb = imgb.shape[:2]
    max_height = np.max([ha, hb])
    total_width = wa + wb
    new_img = np.zeros(shape=(max_height, total_width, 4), dtype=np.uint8)
    new_img.fill(1.0)
    new_img[:ha, :wa] = imga
    new_img[:hb, wa:total_width] = imgb
    return new_img


def concatImageRow(imga, imgb):
    """
	Combines two color image ndarrays side-by-side top to bottom.
	"""
    ha, wa = imga.shape[:2]
    hb, wb = imgb.shape[:2]
    max_width = np.max([wa, wb])
    total_height = ha + hb
    new_img = np.zeros(shape=(total_height, max_width, 4), dtype=np.uint8)
    new_img.fill(1.0)
    new_img[:ha, :wa] = imga
    new_img[ha:total_height, :wb] = imgb
    return new_img


def concatImage(images, cols):
    """
	Combine a list of images together based on the concatImageRow and concatImageCol
	"""
    length = len(images)
    rows = length / cols + 1
    oneRowImage = np.zeros(shape=(0, 0, 4), dtype=np.uint8)
    multiRowImage = np.zeros(shape=(0, 0, 4), dtype=np.uint8)
    for i in range(0, length):
        if (i + 1) % cols == 0:
            oneRowImage = concatImageCol(oneRowImage, images[i])
            multiRowImage = concatImageRow(multiRowImage, oneRowImage)
            oneRowImage = np.zeros(shape=(0, 0, 4), dtype=np.uint8)
        else:
            oneRowImage = concatImageCol(oneRowImage, images[i])
    multiRowImage = concatImageRow(multiRowImage, oneRowImage)
    return multiRowImage


def fig2data(fig):
    """
	@brief Convert a Matplotlib figure to a 4D numpy array with RGBA channels and return it
	@param fig a matplotlib figure
	@return a numpy 3D array of RGBA values
	"""
    # draw the renderer
    canvas = FigureCanvas(fig)
    canvas.draw()
    # Get the RGBA buffer from the figure
    w, h = canvas.get_width_height()
    buf = np.fromstring(canvas.tostring_argb(), dtype=np.uint8)
    buf.shape = (h, w, 4)
    # print(buf[0,0,:])
    # if transparent!=None:
    # 	for i in range(0,h):
    # 		for j in range(0,w):
    # 			if buf[i,j,1]==transparent[0] and buf[i,j,2]==transparent[1] and buf[i,j,3]==transparent[2]:
    # 				buf[i,j,0]=0

    # canvas.tostring_argb give pixmap in ARGB mode. Roll the ALPHA channel to have it in RGBA mode
    # buf = np.moveaxis( buf, 0, -1 )
    buf = np.roll(buf, 3, axis=2)
    return buf


def overlayImage(img1, img2):
    fig = plt.figure(figsize=(img1.shape[1] / 300.0, img1.shape[0] / 300.0), dpi=300)
    im1 = plt.imshow(img1)
    im2 = plt.imshow(img2)
    plt.axis('off')
    plt.close(fig)
    print(img1.shape)
    print(img2.shape)
    return fig2data(fig)


def getConfig(length=1, printGuide=True):
    config = {}
    config.update({'title': ""})
    config.update({'title.size': None})
    config.update({'interpolation': 'none'})
    config.update({'axis': 'off'})
    config.update({'figureSize': None})
    config.update({'resolution': None})
    config.update({'colorMap': 'viridis'})
    config.update({'colorbar.ticks': None})
    config.update({'colorbar.format': None})
    config.update({'colorbar.edge': False})
    config.update({'colorbar.title': ""})
    config.update({'colorbar.title.size': None})
    config.update({'range.x': None})
    config.update({'range.y': None})
    config.update({'label.x': ''})
    config.update({'label.y': ''})
    config.update({'terminal': 'screen'})
    config.update({'line.color': [None] * length})
    config.update({'line.style': [None] * length})
    config.update({'line.width': [None] * length})
    config.update({'line.label': [None] * length})
    config.update({'hist.bins': 10})
    config.update({'hist.cluster': False})
    config.update({'marker.style': [None] * length})
    config.update({'marker.edge.color': [None] * length})
    config.update({'marker.edge.width': [None] * length})
    config.update({'marker.face.color': [None] * length})
    config.update({'marker.size': [None] * length})
    config.update({'legend.display': True})
    config.update({'scalebar.display': True})
    config.update({'scalebar.width': 5})
    config.update({'scalebar.position': (0.5, 0.5)})
    config.update({'scalebar.length': 10})
    config.update({'scalebar.unit': 'nm'})
    config.update({'scalebar.dx': 1.0})
    config.update({'scalebar.color': 'c'})
    config.update({'colorbar.display': 'outside'})

    if printGuide:
        formatString = "%30s : %s"
        print(formatString % ('title', 'string'))
        print(formatString % ('title.size', 'int'))
        print(formatString % ('interpolation ', ' string [none, nearest, bilinear, bicubic, spline16, spline36, hanning, hamming, hermite, kaiser, quadric, catrom, gaussian, bessel, mitchell, sinc, lanczos]'))
        print(formatString % ('axis ', ' string [on, off]'))
        print(formatString % ('figureSize ', ' tuple'))
        print(formatString % ('resolution ', ' int'))
        print(formatString % ('colorMap ', ' string'))
        print(formatString % ('colorbar.ticks ', ' list'))
        print(formatString % ('colorbar.fFormat ', ' format string'))
        print(formatString % ('colorbar.edge ', ' boolean'))
        print(formatString % ('colorbar.title ', ' String'))
        print(formatString % ('colorbar.title.size ', ' int'))
        print(formatString % ('range.x ', ' tuple'))
        print(formatString % ('range.y ', ' tuple'))
        print(formatString % ('label.x ', ' string'))
        print(formatString % ('label.y ', ' string'))
        print(formatString % ('terminal ', ' string [none,screen,file]'))
        print(formatString % ('line.color ', ' list of valid matplotlib color'))
        print(formatString % ('line.style ', ' list of lineStyles [solid | dashed, dashdot, dotted | (offset, on-off-dash-seq) | - | -- | -. | : | None | " " | ""]'))
        print(formatString % ('line.width ', ' list of integers'))
        print(formatString % ('line.label ', ' list of string'))
        print(formatString % ('hist.bins ', ' histogram bins'))
        print(formatString % ('hist.cluster ', ' histogram of cluster analysis'))
        print(formatString % ('marker.style ', ' list of markers https://matplotlib.org/api/markers_api.html#module-matplotlib.markers'))
        print(formatString % ('marker.edge.color ', ' list of valid matplotlib color'))
        print(formatString % ('marker.edge.width ', ' list of integers'))
        print(formatString % ('marker.face.color ', ' list of valid matplotlib color'))
        print(formatString % ('marker.size ', ' list of integers'))
        print(formatString % ('legend.display ', ' boolean'))
        print(formatString % ('scalebar.display ', ' boolean'))
        print(formatString % ('scalebar.width ', ' int'))
        print(formatString % ('scalebar.position ', ' tuple of float'))
        print(formatString % ('scalebar.length ', ' int'))
        print(formatString % ('scalebar.unit ', ' string'))
        print(formatString % ('scalebar.dx ', ' float'))
        print(formatString % ('scalebar.color ', ' valid matplotlib color'))
        print(formatString % ('colorbar.display ', ' string [inside | outside | None]'))

    return copy.deepcopy(config)


def showImageFromArray(data):
    w = data.shape[0] / 300.0
    h = data.shape[1] / 300.0
    plt.figure(figsize=(h, w), dpi=300)
    print(w)
    print(h)
    print(data.shape)
    plt.imshow(data)
    plt.axis('off')
    plt.show()


def saveImageFromArray(data, imageName, resolution):
    w = data.shape[0] / 300
    h = data.shape[1] / 300
    fig = plt.figure(figsize=(h, w), dpi=resolution)
    plt.imshow(data)
    plt.axis('off')
    plt.savefig(imageName, dpi=resolution)
    plt.close(fig)


def printAllColorMap():
    # print all possible color map
    cmaps['Perceptually Uniform Sequential'] = ['viridis', 'plasma', 'inferno', 'magma']

    cmaps['Sequential'] = ['Greys', 'Purples', 'Blues', 'Greens', 'Oranges', 'Reds', 'YlOrBr', 'YlOrRd', 'OrRd', 'PuRd', 'RdPu', 'BuPu', 'GnBu', 'PuBu', 'YlGnBu', 'PuBuGn', 'BuGn', 'YlGn']
    cmaps['Sequential (2)'] = ['binary', 'gist_yarg', 'gist_gray', 'gray', 'bone', 'pink', 'spring', 'summer', 'autumn', 'winter', 'cool', 'Wistia', 'hot', 'afmhot', 'gist_heat', 'copper']
    cmaps['Diverging'] = ['PiYG', 'PRGn', 'BrBG', 'PuOr', 'RdGy', 'RdBu', 'RdYlBu', 'RdYlGn', 'Spectral', 'coolwarm', 'bwr', 'seismic']
    cmaps['Qualitative'] = ['Pastel1', 'Pastel2', 'Paired', 'Accent', 'Dark2', 'Set1', 'Set2', 'Set3', 'tab10', 'tab20', 'tab20b', 'tab20c']
    cmaps['Miscellaneous'] = ['flag', 'prism', 'ocean', 'gist_earth', 'terrain', 'gist_stern', 'gnuplot', 'gnuplot2', 'CMRmap', 'cubehelix', 'brg', 'hsv', 'gist_rainbow', 'rainbow', 'jet', 'nipy_spectral', 'gist_ncar']

    nrows = max(len(cmap_list) for cmap_category, cmap_list in cmaps.items())
    fig = []
    for cmap_category, cmap_list in cmaps.items():
        hold = fig2data(plot_color_gradients(cmap_category, cmap_list, nrows))
        # print(hold.shape)
        # plt.figure(figsize=(3,2),dpi=300)
        # plt.imshow(hold)
        # plt.show()
        fig.append(hold)

    final = concatImage(fig, 3)
    showImageFromArray(final)
    mpl.image.imsave("colormaps.png", final)


def createScaleBar(config, positionBox=[0, 0, 1, 1], alone=True):
    figureSize = config['figureSize']
    resolution = config['resolution']
    rangeX = config['range.x']
    rangeY = config['range.y']
    display = config['scalebar.display']
    terminal = config['terminal']
    length = config['scalebar.length']
    position = config['scalebar.position']
    unit = config['scalebar.unit']
    dx = config['scalebar.dx']
    width = config['scalebar.width']
    scalebarColor = config['scalebar.color']

    # if rangeX != None:
    x = position[0] * (rangeX[1] - rangeX[0]) + rangeX[0]
    # else:
    # x=position[0]*dim[0]

    # if rangeY != None:
    y = position[1] * (rangeY[1] - rangeY[0]) + rangeY[0]
    # else:
    # y=position[1]*dim[1]

    linePosX = [x - length / 2.0, x + length / 2.0]
    linePosY = [y, y]

    # cax=ax.imshow(data.transpose(),cmap=colorMap,origin='lower',interpolation=interpolationType)
    # fig.gca().set_aspect('equal',adjustable='box')
    # cbar=fig.colorbar(cax,ticks=colorbarTicks,format=colorbarFormat,drawedges=colorbarEdge)
    # cbar.ax.set_title(colorbarTitle,fontsize=colorbarTitleSize)

    scaletext = str(length / dx) + unit
    fig, ax = plt.subplots(figsize=figureSize, dpi=resolution)
    fig.gca().set_aspect('equal', adjustable='box')
    ax.axis('off')

    ax.set_xlim(rangeX)
    ax.set_ylim(rangeY)
    # print(ax.get_position())
    # print(ax.get_position().x0)
    # print(ax.get_position().ymin)
    # print(ax.get_ylim())
    # print(dir(ax.get_position()))
    # print(fig.get_size_inches())
    l1 = mpl.lines.Line2D(linePosX, linePosY, linewidth=width, color=scalebarColor)

    # fig.lines.extend([l1])
    # fig.canvas.draw()
    textPosX = x
    box = ax.get_position()
    yPixel = fig.get_dpi() * fig.get_size_inches()[1]
    textPosY = y + (box.y1 - box.y0) * yPixel / (ax.get_ylim()[1] - ax.get_ylim()[0]) * width
    textPosY = y + (width + 1) * 72.0 / fig.get_dpi()
    # print(yPixel)
    # print(width)
    # print((box.y1-box.y0)*yPixel/(ax.get_ylim()[1]-ax.get_ylim()[0])*width)
    ax.add_line(l1)
    ax.text(textPosX, textPosY, scaletext, horizontalalignment='center', verticalalignment='center')

    plt.tight_layout()
    ax.set_position(positionBox)
    print(ax.get_position())

    if alone:
        if terminal == "screen":
            plt.show()
        elif terminal == "file":
            plt.savefig(imageName, dpi=resolution, transparent=True)
        elif terminal == 'none':
            plt.close(fig)
        return fig2data(fig)
    else:
        plt.savefig('temp.png', dpi=resolution, transparent=True)
        png = mpl.image.imread('temp.png')
        plt.close(fig)
        os.remove('temp.png')
        return png


def createColorBar(data, config, alone=True):
    dim = data.shape
    # check if the data size is 2 dimensional
    if len(dim) != 2:
        print("The data input is not a 2 dimension")
        exit()

    # obtain parameters from the config
    titleText = config['title']
    titleFontSize = config['title.size']
    interpolationType = config['interpolation']
    axisSwitch = config['axis']
    figureSize = config['figureSize']
    resolution = config['resolution']
    colorMap = config['colorMap']
    colorbarTicks = config['colorbar.ticks']
    colorbarFormat = config['colorbar.format']
    colorbarEdge = config['colorbar.edge']
    colorbarTitle = config['colorbar.title']
    colorbarTitleSize = config['colorbar.title.size']
    rangeX = config['range.x']
    rangeY = config['range.y']
    labelX = config['label.x']
    labelY = config['label.y']
    terminal = config['terminal']
    scalebarDisplay = config['scalebar.display']
    colorbarDisplay = config['colorbar.display']

    fig, ax = plt.subplots(figsize=figureSize, dpi=resolution)

    cax = ax.imshow(data.transpose(), cmap=colorMap, origin='lower', interpolation=interpolationType)
    fig.gca().set_aspect('equal', adjustable='box')
    cbar = fig.colorbar(cax, ticks=colorbarTicks, format=colorbarFormat, drawedges=colorbarEdge)
    cbar.ax.set_title(colorbarTitle, fontsize=colorbarTitleSize)

    ax.axis(axisSwitch)
    ax.set_title(titleText, fontsize=titleFontSize)
    ax.set_xlim(rangeX)
    ax.set_ylim(rangeY)
    ax.set_xlabel(labelX)
    ax.set_ylabel(labelY)

    if colorbarDisplay == 'outside':
        fig.gca().set_visible(False)
        plt.tight_layout()
    elif colorbarDisplay == 'inside':
        plt.tight_layout()
        fig.gca().set_visible(False)

    heat = fig2data(fig)
    if alone:
        if terminal == "screen":
            plt.show()
        elif terminal == "file":
            plt.savefig(imageName, dpi=resolution, transparent=True)
        elif terminal == 'none':
            plt.close(fig)
        return fig2data(fig)
    else:
        plt.savefig('temp.png', dpi=resolution, transparent=True)
        png = mpl.image.imread('temp.png')
        plt.close(fig)
        os.remove('temp.png')
        return png


def heatPlot(data, config, imageName=""):
    dim = data.shape
    # check if the data size is 2 dimensional
    if len(dim) != 2:
        print("The data input is not a 2 dimension")
        exit()

    # obtain parameters from the config
    titleText = config['title']
    titleFontSize = config['title.size']
    interpolationType = config['interpolation']
    axisSwitch = config['axis']
    figureSize = config['figureSize']
    resolution = config['resolution']
    colorMap = config['colorMap']
    colorbarTicks = config['colorbar.ticks']
    colorbarFormat = config['colorbar.format']
    colorbarEdge = config['colorbar.edge']
    colorbarTitle = config['colorbar.title']
    colorbarTitleSize = config['colorbar.title.size']
    rangeX = config['range.x']
    rangeY = config['range.y']
    labelX = config['label.x']
    labelY = config['label.y']
    display = config['terminal']
    scalebarDisplay = config['scalebar.display']
    colorbarDisplay = config['colorbar.display']

    fig, ax = plt.subplots(figsize=figureSize, dpi=resolution)
    cax = ax.imshow(data.transpose(), cmap=colorMap, origin='lower', interpolation=interpolationType)
    fig.gca().set_aspect('equal', adjustable='box')
    ax.axis(axisSwitch)
    ax.set_title(titleText, fontsize=titleFontSize)
    ax.set_xlim(rangeX)
    ax.set_ylim(rangeY)
    ax.set_xlabel(labelX)
    ax.set_ylabel(labelY)

    if colorbarDisplay:
        # colorbar=createColorBar(data,config,alone=False)
        cbar = fig.colorbar(cax, ticks=colorbarTicks, format=colorbarFormat, drawedges=colorbarEdge)
        cbar.ax.set_title(colorbarTitle, fontsize=colorbarTitleSize)

    plt.tight_layout()

    left = ax.get_position().x0
    bot = ax.get_position().y0
    width = ax.get_position().x1 - ax.get_position().x0
    height = ax.get_position().y1 - ax.get_position().y0

    heat = fig2data(fig)

    # showImageFromArray(heat)
    if scalebarDisplay:
        configHold = copy.deepcopy(config)
        configHold['range.x'] = ax.get_xlim()
        configHold['range.y'] = ax.get_ylim()
        scalebar = createScaleBar(configHold, [left, bot, width, height], alone=False)
        # showImageFromArray(scalebar)
        heat = overlayImage(heat, scalebar)

    # if colorbarDisplay:
    # 	heat=overlayImage(heat,colorbar)

    if display == 'none':
        plt.close(fig)
    if display == "screen":
        plt.close(fig)
        showImageFromArray(heat)
    elif display == "file":
        plt.close(fig)
        saveImageFromArray(heat, imageName, resolution)
    return heat
    # else:
    # 	if display == "screen":
    # 		plt.show()
    # 	elif display == "file":
    # 		plt.savefig(imageName,dpi=resolution)
    # 	return heat


def heatPlotWithDisp(data, disp, config, imageName=""):
    dim = data.shape
    # check if the data size is 2 dimensional
    if len(dim) != 2:
        print("The data input is not a 2 dimension")
        exit()

    # obtain parameters from the config
    titleText = config['title']
    titleFontSize = config['title.size']
    interpolationType = config['interpolation']
    axisSwitch = config['axis']
    figureSize = config['figureSize']
    resolution = config['resolution']
    colorMap = config['colorMap']
    colorbarTicks = config['colorbar.ticks']
    colorbarFormat = config['colorbar.format']
    colorbarEdge = config['colorbar.edge']
    colorbarTitle = config['colorbar.title']
    colorbarTitleSize = config['colorbar.title.size']
    rangeX = config['range.x']
    rangeY = config['range.y']
    labelX = config['label.x']
    labelY = config['label.y']
    display = config['terminal']
    scalebarDisplay = config['scalebar.display']
    colorbarDisplay = config['colorbar.display']

    fig, ax = plt.subplots(figsize=figureSize, dpi=resolution)
    cax = ax.pcolor(disp[0], disp[1], data, cmap=colorMap)
    fig.gca().set_aspect('equal', adjustable='box')
    ax.axis(axisSwitch)
    ax.set_title(titleText, fontsize=titleFontSize)
    ax.set_xlim(rangeX)
    ax.set_ylim(rangeY)
    ax.set_xlabel(labelX)
    ax.set_ylabel(labelY)

    if colorbarDisplay:
        # colorbar=createColorBar(data,config,alone=False)
        cbar = fig.colorbar(cax, ticks=colorbarTicks, format=colorbarFormat, drawedges=colorbarEdge)
        cbar.ax.set_title(colorbarTitle, fontsize=colorbarTitleSize)

    plt.tight_layout()

    left = ax.get_position().x0
    bot = ax.get_position().y0
    width = ax.get_position().x1 - ax.get_position().x0
    height = ax.get_position().y1 - ax.get_position().y0

    heat = fig2data(fig)

    # showImageFromArray(heat)
    print(scalebarDisplay)
    if scalebarDisplay:
        configHold = copy.deepcopy(config)
        configHold['range.x'] = ax.get_xlim()
        configHold['range.y'] = ax.get_ylim()
        scalebar = createScaleBar(configHold, [left, bot, width, height], alone=False)
        # showImageFromArray(scalebar)
        heat = overlayImage(heat, scalebar)

    # if colorbarDisplay:
    # 	heat=overlayImage(heat,colorbar)
    plt.close(fig)
    print(display)

    if display == 'none':
        # plt.close(fig)
        print("nothing")
    if display == "screen":
        showImageFromArray(heat)
        if imageName != '':
            saveImageFromArray(heat, imageName, resolution)
    elif display == "file":
        # plt.close(fig)
        saveImageFromArray(heat, imageName, resolution)
    return heat

    # else:
    # 	if display == "screen":
    # 		plt.show()
    # 	elif display == "file":
    # 		plt.savefig(imageName,dpi=resolution)
    # 	return heat


def lineListPlot(data, config, imageName=''):
    dim = data.shape
    Y = []
    # check if the data size is 2 dimensional
    if len(dim) == 1:
        length = dim[0]
        X = np.linspace(1, length, length)
        Y.append(data)
    elif len(dim) == 2:
        length = dim[1]
        X = np.linspace(1, length, length)
        for i in range(0, dim[0]):
            Y.append(data[i, :])
    else:
        print("The data input is larger than 2 dimensional")
        exit()

    # obtain parameters from the config
    titleText = config['title']
    titleFontSize = config['title.size']
    interpolationType = config['interpolation']
    axisSwitch = config['axis']
    figureSize = config['figureSize']
    resolution = config['resolution']
    colorMap = config['colorMap']
    colorbarTicks = config['colorbar.ticks']
    colorbarFormat = config['colorbar.format']
    colorbarEdge = config['colorbar.edge']
    colorbarTitle = config['colorbar.title']
    colorbarTitleSize = config['colorbar.title.size']
    rangeX = config['range.x']
    rangeY = config['range.y']
    labelX = config['label.x']
    labelY = config['label.y']
    display = config['terminal']
    lineColor = config['line.color']
    lineStyle = []
    lineStyle = config['line.style']
    lineLabel = []
    lineLabel = config['line.label']
    lineWidth = []
    lineWidth = config['line.width']
    markerStyle = []
    markerStyle = config['marker.style']
    markerSize = []
    markerSize = config['marker.size']
    markerEdgeColor = []
    markerEdgeColor = config['marker.edge.color']
    markerEdgeWidth = []
    markerEdgeWidth = config['marker.edge.width']
    markerFaceColor = []
    markerFaceColor = config['marker.face.color']
    showLegend = config['legend.display']

    fig, ax = plt.subplots(figsize=figureSize, dpi=resolution)

    for i in range(0, len(Y)):
        ax.plot(X, Y[i], color=lineColor[i], linestyle=lineStyle[i], linewidth=lineWidth[i], label=lineLabel[i], marker=markerStyle[i], markeredgecolor=markerEdgeColor[i], markeredgewidth=markerEdgeWidth[i], markerfacecolor=markerFaceColor[i], markersize=markerSize[i])

    ax.axis(axisSwitch)
    ax.set_title(titleText, fontsize=titleFontSize)
    ax.set_xlim(rangeX)
    ax.set_ylim(rangeY)
    ax.set_xlabel(labelX)
    ax.set_ylabel(labelY)

    if showLegend:
        plt.legend()

    plt.tight_layout()

    if display == "screen":
        plt.show()
    elif display == "file":
        plt.savefig(imageName, dpi=resolution)
    elif display == 'none':
        plt.close(fig)

    return fig2data(fig)


def lineXYPlot(data, config, imageName=''):
    dim = data.shape
    X = []
    Y = []
    # check if the data size is 2 dimensional
    if len(dim) == 2:
        if dim[0] != 2:
            print("The 2D data should have only two rows, first for x and second for y, example numpy.array([x,y])")
            exit()
        X.append(data[0, :])
        Y.append(data[1, :])
    elif len(dim) == 3:
        if dim[1] != 2:
            print("The 3D data, first dimension is for different x-y pairs, second dimension should be of length 2, first for x and second for y, and last dimension for values in x/y, example numpy.array([[x1,y1],[x,y]])")
            exit()
        for i in range(0, dim[0]):
            X.append(data[i, 0, :])
            Y.append(data[i, 1, :])
    else:
        print("The data input is not 2 or 3 dimensional")
        exit()

    # obtain parameters from the config
    titleText = config['title']
    titleFontSize = config['title.size']
    interpolationType = config['interpolation']
    axisSwitch = config['axis']
    figureSize = config['figureSize']
    resolution = config['resolution']
    colorMap = config['colorMap']
    colorbarTicks = config['colorbar.ticks']
    colorbarFormat = config['colorbar.format']
    colorbarEdge = config['colorbar.edge']
    colorbarTitle = config['colorbar.title']
    colorbarTitleSize = config['colorbar.title.size']
    rangeX = config['range.x']
    rangeY = config['range.y']
    labelX = config['label.x']
    labelY = config['label.y']
    display = config['terminal']
    lineColor = config['line.color']
    lineStyle = []
    lineStyle = config['line.style']
    lineLabel = []
    lineLabel = config['line.label']
    lineWidth = []
    lineWidth = config['line.width']
    markerStyle = []
    markerStyle = config['marker.style']
    markerSize = []
    markerSize = config['marker.size']
    markerEdgeColor = []
    markerEdgeColor = config['marker.edge.color']
    markerEdgeWidth = []
    markerEdgeWidth = config['marker.edge.width']
    markerFaceColor = []
    markerFaceColor = config['marker.face.color']
    showLegend = config['legend.display']

    fig, ax = plt.subplots(figsize=figureSize, dpi=resolution)

    for i in range(0, len(Y)):
        ax.plot(X[i], Y[i], color=lineColor[i], linestyle=lineStyle[i], linewidth=lineWidth[i], label=lineLabel[i], marker=markerStyle[i], markeredgecolor=markerEdgeColor[i], markeredgewidth=markerEdgeWidth[i], markerfacecolor=markerFaceColor[i], markersize=markerSize[i])

    ax.axis(axisSwitch)
    ax.set_title(titleText, fontsize=titleFontSize)
    ax.set_xlim(rangeX)
    ax.set_ylim(rangeY)
    ax.set_xlabel(labelX)
    ax.set_ylabel(labelY)

    if showLegend:
        plt.legend()

    plt.tight_layout()

    if display == "screen":
        plt.show()
    elif display == "file":
        plt.savefig(imageName, dpi=resolution)
    elif display == 'none':
        plt.close(fig)

    return fig2data(fig)


def histPlot(data, config, imageName=''):
    dim = data.shape
    X = []
    # check if the data size is 2 dimensional
    if len(dim) == 4:
        for i in dim[3]:
            X[i] = data[:, :, :, i].flatten()
    elif len(dim) == 3:
        X = data.flatten()
    else:
        print("The data input is not 2 or 3 dimensional")
        exit()
    # obtain parameters from the config
    titleText = config['title']
    titleFontSize = config['title.size']
    interpolationType = config['interpolation']
    axisSwitch = config['axis']
    figureSize = config['figureSize']
    resolution = config['resolution']
    colorMap = config['colorMap']
    colorbarTicks = config['colorbar.ticks']
    colorbarFormat = config['colorbar.format']
    colorbarEdge = config['colorbar.edge']
    colorbarTitle = config['colorbar.title']
    colorbarTitleSize = config['colorbar.title.size']
    display = config['terminal']
    labelX = config['label.x']
    labelY = config['label.y']
    n_bins = config['hist.bins']
    cluster = config['hist.cluster']

    fig, ax = plt.subplots(figsize=figureSize, dpi=resolution)

    ax.hist(X, bins=n_bins)

    ax.axis(axisSwitch)
    ax.set_title(titleText, fontsize=titleFontSize)
    ax.set_xlabel(labelX)
    ax.set_ylabel(labelY)

    plt.tight_layout()

    if display == "screen":
        plt.show()
    elif display == "file":
        plt.savefig(imageName, dpi=resolution)
    elif display == 'none':
        plt.close(fig)

    return fig2data(fig)


def boxPlot(data, config):
    dim = data.shape
    X = []
    Y = []
    # check if the data size is 2 dimensional
    if len(dim) == 2:
        if dim[0] != 2:
            print("The 2D data should have only two rows, first for x and second for y, example numpy.array([x,y])")
            exit()
        X.append(data[0, :])
        Y.append(data[1, :])
    elif len(dim) == 3:
        if dim[1] != 2:
            print("The 3D data, first dimension is for different x-y pairs, second dimension should be of length 2, first for x and second for y, and last dimension for values in x/y, example numpy.array([[x1,y1],[x,y]])")
            exit()
        for i in range(0, dim[0]):
            X.append(data[i, 0, :])
            Y.append(data[i, 1, :])
    else:
        print("The data input is not 2 or 3 dimensional")
        exit()

    # obtain parameters from the config
    titleText = config['title']
    titleFontSize = config['title.size']
    interpolationType = config['interpolation']
    axisSwitch = config['axis']
    figureSize = config['figureSize']
    resolution = config['resolution']
    colorMap = config['colorMap']
    colorbarTicks = config['colorbar.ticks']
    colorbarFormat = config['colorbar.format']
    colorbarEdge = config['colorbar.edge']
    colorbarTitle = config['colorbar.title']
    colorbarTitleSize = config['colorbar.title.size']
    rangeX = config['range.x']
    rangeY = config['range.y']
    labelX = config['label.x']
    labelY = config['label.y']
    display = config['terminal']
    lineColor = config['line.color']
    lineStyle = []
    lineStyle = config['line.style']
    lineLabel = []
    lineLabel = config['line.label']
    lineWidth = []
    lineWidth = config['line.width']
    markerStyle = []
    markerStyle = config['marker.style']
    markerSize = []
    markerSize = config['marker.size']
    markerEdgeColor = []
    markerEdgeColor = config['marker.edge.color']
    markerEdgeWidth = []
    markerEdgeWidth = config['marker.edge.width']
    markerFaceColor = []
    markerFaceColor = config['marker.face.color']
    showLegend = config['legend.display']

    fig, ax = plt.subplots(figsize=figureSize, dpi=resolution)

    for i in range(0, len(Y)):
        ax.plot(X[i], Y[i], color=lineColor[i], linestyle=lineStyle[i], linewidth=lineWidth[i], label=lineLabel[i], marker=markerStyle[i], markeredgecolor=markerEdgeColor[i], markeredgewidth=markerEdgeWidth[i], markerfacecolor=markerFaceColor[i], markersize=markerSize[i])

    ax.axis(axisSwitch)
    ax.set_title(titleText, fontsize=titleFontSize)
    ax.set_xlim(rangeX)
    ax.set_ylim(rangeY)
    ax.set_xlabel(labelX)
    ax.set_ylabel(labelY)

    if showLegend:
        plt.legend()

    plt.tight_layout()

    if display == "screen":
        plt.show()
    elif display == "file":
        plt.savefig(imageName, dpi=resolution)
    elif display == 'none':
        plt.close(fig)

    return fig2data(fig)
