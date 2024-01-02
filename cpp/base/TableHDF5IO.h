/* #include "H5Cpp.h" */
#include "hdf5.h"
#include "hdf5_hl.h"
#include <fstream>
#include <sstream>
#include <string.h>
#include <vector>
#include <FreeFormatOneLine.h>
#include <FreeFormatParser.h>
#include <json.hpp>
#include <H5File.h>
#ifndef TABLEHDF5IO_H
#define TABLEDF5IO_H

using namespace std;
using json = nlohmann::json;
class TableHDF5IO : public H5File{
    private:
        /* std::string datFileName,headerLine,fileType; // h5FileName */
        std::string headerLine;//,fileType; // h5FileName
        vector<vector<string> > wholeList;
        int tableLength,fieldLength,chunkSize;
        int stringSize;
        /* std::string trim(std::string str); */
    public:
        TableHDF5IO();
        ~TableHDF5IO();
        /* void setDatFileName(std::string); */
        /* void setH5FileName(std::string); */
        void readFreeFormatFile();
        void readFixFormatFile();
        void readTimeDependentFile();
        void readJSONFile();
        void readH5File(std::string groupName);
        void outputH5(std::string groupName);
        void outputFreeFormatFile();
        void outputFixFormatFile();
        void outputTimeDependentFile();
        void outputJSONFile();
        void outputAuto();
        void cleanDat();
        void setChunkSize(int);
        json convertVec2JSON(vector<vector<std::string>>, std::string,std::string);
        int parseJObject(json j,std::string parent,std::string listIndex);
};

#endif
