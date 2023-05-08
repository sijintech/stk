#include <FerroDomain.h>
#include <string>
#include <fstream>
#include <sstream>
#include <iostream>
#include <vtkXMLImageDataWriter.h>
#include <vtkImageData.h>
#include <vtkSmartPointer.h>
#include <vtkDoubleArray.h>
#include <vtkPointData.h>


using namespace std;

#ifndef MUDATASET_H
#define MUDATASET_H

class MuDataset{
    public:
        MuDataset();
        MuDataset(string);
        ~MuDataset();

        void readDatFile();
        void setDatFileName(string);
        string getDatFileName();
        string getVTKFileName();
        string getVTIFileName();
        void setVTKFileName(string);
        void setVTIFileName(string);
        /* void readVTKFile(); */
        void outputVTKFile();
        void outputVTIFile();
        void outputDomainVTIFile(FerroDomain);
        void setDimension(int,int,int,int);
        double **** getData();
        int * getDimension(int *dim);
    private:
        string datFileName="";
        string vtkFileName="";
        string vtiFileName="";
        string fileName;
        double **** data;
        double * domainPercent;
        int x=0,y=0,z=0,col=0;
        
};
#endif
