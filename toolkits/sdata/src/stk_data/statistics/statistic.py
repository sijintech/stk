from ..data_handling import readDat as rd
import numpy as np


def getAvg(filename):
    data = rd.readDatScalar(filename)
    dim = data.shape
    if len(dim) != 4:
        print("The data file is not 3D")
    avg = np.zeros(dim[3])
    for i in range(0, dim[3]):
        avg[i] = np.average(data[:, :, :, i])
    return avg


def getMax(filename):
    data = rd.readDatScalar(filename)
    dim = data.shape
    if len(dim) != 4:
        print("The data file is not 3D")
    maximum = np.zeros(dim[3])
    for i in range(0, dim[3]):
        maximum[i] = np.maximum(data[:, :, :, i])
    return maximum


def getMin(filename):
    data = rd.readDatScalar(filename)
    dim = data.shape
    if len(dim) != 4:
        print("The data file is not 3D")
    minimum = np.zeros(dim[3])
    for i in range(0, dim[3]):
        minimum[i] = np.minimum(data[:, :, :, i])
    return minimum


def getPercentile(filename, percent):
    data = rd.readDatScalar(filename)
    dim = data.shape
    if len(dim) != 4:
        print("The data file is not 3D")
    percentile = np.zeros(dim[3])
    for i in range(0, dim[3]):
        percentile[i] = np.percentile(data[:, :, :, i], percent)
    return percentile
