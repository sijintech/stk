#include <vector>
#include <string.h>
#include <hdf5.h>
#include <fstream>
#include <sstream>
#include <iostream>
#ifndef H5FILE
#define H5FILE

struct dataset{
    std::string groupName;
    std::string dataName;
    std::string wholeName;
    std::string fileType;
};

struct attr{
    std::string dataName;
    std::string attributeName;
    std::string attributeValue;
};
class H5File{
    protected:
        std::string h5FileName,datFileName,fileType;
        bool file_open,group_open;
    private:
        hid_t file_id,group_id,dataset_id;
        std::vector<dataset> dataList;
        std::vector<std::string> groupList;
        std::vector<attr> attributeList;
        std::vector<attr> scanAttribute(hid_t,std::string);
        void scanGroup(hid_t,std::string);
    public:
        H5File();
        ~H5File();
        void setH5FileName(std::string);
        void getH5FileName(std::string);
        void parseH5File();
        /* void getDataType(hid_t); */
        void writeStrAttribute(hid_t,std::string,std::string);
        void H5FGclose();
        void addRootComment(std::string,std::string);
        std::string readRootComment(std::string);
        void setDatFileName(std::string);
        void clear();
        std::string getTrueGroupName(std::string);
        virtual void outputH5(std::string){};
        std::string readStrAttribute(hid_t,std::string);
        std::string trim(std::string);
        std::vector<dataset> getDatasetList(std::string);
        std::vector<std::string> getGroupList();
        hid_t openH5File(bool);
        hid_t openH5Group(std::string,bool);
        hid_t openH5Data(std::string);
};
#endif
