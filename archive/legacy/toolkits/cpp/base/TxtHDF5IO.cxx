#include <TxtHDF5IO.h>

TxtHDF5IO::TxtHDF5IO(){
    lineNum = 0;
    headerLine = "";
}

void TxtHDF5IO::cleanDat(){
    clear();
    lineNum = 0;
    headerLine = "";
}


TxtHDF5IO::~TxtHDF5IO(){
}

void TxtHDF5IO::outputTXT(){
   ofstream output;
   output.open(datFileName);
   if (headerLine!="") {
       output << headerLine << std::endl;
   }
   for (int i = 0; i < strList.size(); i++) {
       output << strList[i] << endl;
   }
   output.close();
}

void TxtHDF5IO::readH5File(std::string groupName){
    hid_t file_id,group_id,dataset_id,dataspace_id,plist_id,string_type1024;
    herr_t status;
    std::string wholeGroupName,wholeDataName;
    wholeGroupName = getTrueGroupName(groupName);
    wholeDataName = wholeGroupName + '/' + datFileName;
    file_id = openH5File(false);
    /* cout << "after fil open" << endl; */
    group_id = openH5Group(wholeGroupName,false);
    /* cout << "after group open" << endl; */
    dataset_id = H5Dopen(group_id,datFileName.c_str(),H5P_DEFAULT);
    /* cout << "after data open" << endl; */
    plist_id =H5Dget_create_plist(dataset_id);
    string_type1024=H5Tcopy(H5T_C_S1);
    H5Tset_size(string_type1024,1024);
    dataspace_id = H5Dget_space(dataset_id);
    const int ndims = H5Sget_simple_extent_ndims(dataspace_id);
    hsize_t dims[ndims];
    H5Sget_simple_extent_dims(dataspace_id,dims,NULL);
    lineNum = dims[0];
    /* cout << "linenum" << lineNum << endl; */
    char dataHold[lineNum][1024];
    /* cout << "before string read" << endl; */
    status = H5Dread(dataset_id,string_type1024,H5S_ALL,H5S_ALL,H5P_DEFAULT,dataHold);

    strList.clear();
    std::string stringHold;
    /* cout << "before string hold" << endl; */
    for (int i = 0; i < lineNum; i++) {
        stringHold = trim(dataHold[i]);
        strList.push_back(stringHold);
    }
    H5Dclose(dataset_id);
    H5Sclose(dataspace_id);
    H5FGclose();
}

void TxtHDF5IO::outputH5(std::string groupName){
   hid_t file_id,group_id,dataset_id,dataspace_id,plist_id;
   hid_t string_type1024;
   herr_t status;
   hsize_t dims[1],cdims[1];

   file_id = openH5File(true);
   group_id = openH5Group(groupName,true);
    dims[0]=lineNum;
    cdims[0]=lineNum;
    dataspace_id = H5Screate_simple(1,dims,NULL);
    string_type1024 = H5Tcopy(H5T_C_S1);
    H5Tset_size(string_type1024, 1024);
    plist_id = H5Pcreate(H5P_DATASET_CREATE);
    status = H5Pset_chunk(plist_id,1,cdims);
    status = H5Pset_deflate(plist_id,6);
    dataset_id = H5Dcreate(group_id,datFileName.c_str(),string_type1024,dataspace_id,H5P_DEFAULT,plist_id,H5P_DEFAULT);
    char  dataHold[lineNum][1024];
    for (int i = 0; i < lineNum; i++) {
        strcpy(dataHold[i],strList[i].c_str());
    }
    status = H5Dwrite(dataset_id,string_type1024,H5S_ALL,H5S_ALL,H5P_DEFAULT,dataHold);
    fileType = "TXT";
    writeStrAttribute(dataset_id,"File Type",fileType);
    H5Dclose(dataset_id);
    H5Sclose(dataspace_id);
    H5FGclose();
}

void TxtHDF5IO::readTXTFile(){
    std::string line;
    ifstream txtFile(datFileName,std::ifstream::in);
    stringstream ss;
    strList.clear();
    lineNum = 0;
    while(getline(txtFile,line)){
        strList.push_back(line);
        lineNum ++ ;
    }
    txtFile.close();
}
