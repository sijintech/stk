// This is the base class for data, scalar type
#include <string>
#include <fstream>
#include <sstream>
#include <iostream>
#include <vtkXMLImageDataWriter.h>
#include <vtkImageData.h>
#include <vtkSmartPointer.h>
#include <vtkDoubleArray.h>
#include <vtkPointData.h>
#include <vector>


using namespace std;

#ifndef DATASET_H
#define DATASET_H

class Dataset{
    public:
        Dataset();
        Dataset(string);
        ~Dataset();

        void readDatFile();
        void setDatFileName(string);
        string getDatFileName();
        string getVTKFileName();
        string getVTIFileName();
        string getShortFileName();
        string getLongFileName();
        void setVTKFileName(string);
        void setVTIFileName(string);
        /* void readVTKFile(); */
        void outputVTKFile();
        void outputVTIFile();
        void setDimension(int,int,int,int);
        double **** getData();
        int * getDimension(int *dim);
        vector<double> getMin();
        vector<double> getMax();
    protected:
        string datFileName;
        string vtkFileName;
        string vtiFileName;
        string shortFileName;
        string longFileName;
        vector<double> valueMin,valueMax;
        double **** data;
        /* double * domainPercent; */
        int x=0,y=0,z=0,col=0;
        
};
#endif
