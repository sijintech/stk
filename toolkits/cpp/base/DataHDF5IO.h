#include "hdf5.h"
#include <fstream>
#include <sstream>
#include <iostream>
#include <string>
#include <vector>
#include <iomanip>
#include <H5File.h>
#ifndef DATAHDF5IO_H
#define DATAHDF5IO_H

using namespace std;
class DataHDF5IO:public H5File{
    private:
        /* std::string datFileName; */ 
        /* std::string h5FileName; */
        double **** data;
        ofstream output;
        ifstream input;
        int x,y,z,col,chunkX;
    public:
        DataHDF5IO();
        ~DataHDF5IO();
        /* void setDatFileName(std::string); */
        /* void setH5FileName(std::string); */
        void readDat(bool,bool);
        void readH5writeDat(std::string groupName);
        void setChunkX(int);
        void readDatwriteH5(std::string groupName);
        void outputDat(bool,bool,int);
        void cleanDat();
};

#endif
