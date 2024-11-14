#include <DataHDF5IO.h>
#include <TxtHDF5IO.h>
#include <TableHDF5IO.h>
#include <H5File.h>
#include <string.h>
#include <FreeFormatParser.h>
#include <ScreenPrint.h>
#include <FileExist.hpp>

using namespace std;
int main(int argc,char *argv[]){
    DataHDF5IO polarData;
    TableHDF5IO tableData ;//inputData,timeData,potData,fixData;
    TxtHDF5IO txtData;
    H5File hdf5File;
    std::string nameHold,h5Name,strHold,comment;
    FreeFormatParser structRead;
    bool controlFileExist = false;
    ScreenPrint print;
    vector<dataset> dataList;
    vector<vector<string>> firstLevel,secondLevel;
    vector<string> firstHold,secondHold,groupList;

    if (argc > 1) {
        strHold = argv[1];
        if (strHold.substr(strHold.find_last_of(".")+1) == "h5") {
            nameHold = "Reading from " + strHold;
            print.printCenter(nameHold,' ');
            h5Name = strHold;
        }else{
            print.printCenter("File extension is not h5, please use hdf5 file.",' ');
        }
    }else{
        print.printCenter("Using the default backup.h5 file.",' ');
        h5Name = "backup.h5";
    }

    firstHold.clear();
    firstHold.push_back("FILE");
    firstHold.push_back(h5Name);
    firstHold.push_back("");
    firstLevel.push_back(firstHold);
   
    hdf5File.setH5FileName(h5Name);
    hdf5File.parseH5File();
    dataList = hdf5File.getDatasetList("/");
    groupList = hdf5File.getGroupList();

    comment = hdf5File.readRootComment("Comment");
    if (comment != "") {
        /* cout << "inside the comment" << comment << "|"<< endl; */
        firstHold.clear();
        firstHold.push_back("COMMENT");
        firstHold.push_back(comment);
        firstHold.push_back("");
        firstLevel.push_back(firstHold);
    }

    for (auto &it : groupList) {
        if (it != "/") {
            firstHold.clear();
            firstHold.push_back("GROUP");
            firstHold.push_back(removeSlash(it));
            firstHold.push_back("");
            firstLevel.push_back(firstHold);
        }
    }

    for ( auto &it :  dataList) {
        /* cout << "in loop "<<it.groupName << it.dataName << it.fileType << endl; */

        if (it.groupName == "" || it.groupName == "/") {
            firstHold.clear();
            firstHold.push_back(it.fileType);
            firstHold.push_back(it.dataName);
            firstHold.push_back("");
            firstLevel.push_back(firstHold);
        }else{
            secondHold.clear();
            secondHold.push_back(removeSlash(it.groupName));
//            if (it.groupName[0] == '/') {
//                secondHold.push_back(it.groupName.substr(1));
//            }else{
//                secondHold.push_back(it.groupName);
//            }
            secondHold.push_back(it.fileType);
            secondHold.push_back(it.dataName);
            secondHold.push_back("");
            secondLevel.push_back(secondHold);
        }

        /* cout << "in loop"<<it.groupName<<"|" << it.dataName<<"|" << it.fileType << endl; */

        if (it.fileType == "DAT") {
            polarData.setDatFileName(it.dataName);
            polarData.setH5FileName(h5Name);
            polarData.readH5writeDat(it.groupName);
            polarData.cleanDat();

        }else if (it.fileType == "TXT"){
            txtData.setDatFileName(it.dataName);
            txtData.setH5FileName(h5Name);
            txtData.readH5File(it.groupName);
            txtData.outputTXT();
            txtData.cleanDat();

        }else{
            tableData.setDatFileName(it.dataName);
            tableData.setH5FileName(h5Name);
            tableData.readH5File(it.groupName);
            tableData.outputAuto();
            tableData.cleanDat();
        }
    }

    /* cout << "before the wite backup"<< endl; */

    structRead.setFirstWhole(firstLevel);
    structRead.setSecondWhole(secondLevel);
    structRead.write("backupRestore.in");

//    fullName = "Polar.00005000.dat";
//    h5Name = "backup.h5";
//    fullName = "energy_out.dat";
//    timeData.setDatFileName(fullName);
//    timeData.setH5FileName(h5Name);
//    timeData.readH5File("output");
//    timeData.outputTimeDependentFile();
//
//    fullName = "input.in";
//    inputData.setDatFileName(fullName);
//    inputData.setH5FileName(h5Name);
//    inputData.readH5File("input");
//    inputData.outputFreeFormatFile();
//
//    fullName = "pot.in";
//    potData.setDatFileName(fullName);
//    potData.setH5FileName(h5Name);
//    potData.readH5File("input");
//    potData.outputJSONFile();
//
//    fullName = "parameterFormatted.in";
//    fixData.setDatFileName(fullName);
//    fixData.setH5FileName(h5Name);
//    fixData.readH5File("input");
//    fixData.outputFixFormatFile();

    return 0;
}
