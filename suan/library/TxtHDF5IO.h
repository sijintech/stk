#include <H5File.h>
#include <fstream>
#include <sstream>
#include <string.h>
#include <vector>
#ifndef TXTHDF5IO
#define TXTHDF5IO

using namespace std;

class TxtHDF5IO:public H5File{
    private:
        vector<string> strList;
        int lineNum;
        string headerLine;
    public:
        TxtHDF5IO();
        ~TxtHDF5IO();
        void outputH5(string);
        void readTXTFile();
        void outputTXT();
        void readH5File(std::string);
        void cleanDat();
};

#endif
