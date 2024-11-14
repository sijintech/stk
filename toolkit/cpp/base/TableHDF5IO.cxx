#include "TableHDF5IO.h"
#include <iostream>
#include <string.h>

/* using namespace H5; */
using json = nlohmann::json;

typedef struct tableline{
    char name[256];
    char value[2048];
    char comment[256];
} tableline;


TableHDF5IO::TableHDF5IO(){
    tableLength = 0;
    fieldLength = 0;
    chunkSize = 1;
    stringSize = 20;
    /* datFileName = ""; */
    /* setH5FileName( ""); */
    /* h5FileName = ""; */
    headerLine = "";
    /* fileType = ""; */
}

TableHDF5IO::~TableHDF5IO(){
}

void TableHDF5IO::cleanDat(){
    clear();
    for ( auto &it : wholeList ) {
        it.clear();
    }
    wholeList.clear();
    tableLength = 0;
    fieldLength = 0;
    /* datFileName = ""; */
    /* setH5FileName( ""); */
    /* h5FileName = ""; */
    headerLine = "";
    /* fileType = ""; */
}

//void TableHDF5IO::setDatFileName(std::string datFile){
//    datFileName = datFile;
//}

//void TableHDF5IO::setH5FileName(std::string h5File){
//    h5FileName = h5File;
//}

int TableHDF5IO::parseJObject(json j,std::string parent, std::string listIndex){
    vector<std::string> vectorHold(6);
    int lengthHold = wholeList.size();
    for (json::iterator it = j.begin(); it != j.end(); it++) {
        json j1 = it.value();
        /* std::cout << it.key() << " sep " <<it.value() <<std::endl; */
        vectorHold[0] = parent; // parent
        vectorHold[1] = it.key(); // key
        vectorHold[2] = " "; // type
        vectorHold[3] = listIndex;  // array index
        vectorHold[4] = " "; // length
        vectorHold[5] = " "; // value


        if (j1.is_object()) {
            parseJObject(j1,it.key()," ");
            vectorHold[2] = "Object";
            vectorHold[4] = std::to_string(j1.size());
            /* std::cout << "is object" << std::endl; */
        }else if(j1.is_array()) {
            for (int i = 0; i < j1.size(); i++) {
                json j2 = j1[i];
                parseJObject(j2,it.key(),std::to_string(i));
            }
            vectorHold[2] = "List";
            vectorHold[4] = std::to_string(j1.size());
            /* std::cout << "is list" << std::endl; */
        }else if(j1.is_string()) {
            vectorHold[2] = "String";
            vectorHold[5] = it.value();
            /* std::cout << "is string" << vectorHold[5] << std::endl; */
        }else if(j1.is_number()) {
            double doubleHold = it.value();
            vectorHold[2] = "Number";
            vectorHold[5] = std::to_string(doubleHold);
            /* std::cout << "is number" << std::endl; */

        }
        wholeList.push_back(vectorHold);
        /* cout << "inside parse" << wholeList.size() << endl; */
    }

    return lengthHold - wholeList.size();
}

void TableHDF5IO::readJSONFile(){
    std::ifstream file(datFileName);
    json j;
    file >> j;
    vector<string> vectorHold[6];
    fieldLength = 6;
    headerLine = "Parent, Key, Type, List Index, Length, Value";
    wholeList.clear();
    parseJObject(j,"root"," ");
    tableLength = wholeList.size();
    stringSize = 256;
    fileType = "JSON";
    /* cout << "length " << tableLength << endl; */
}

void TableHDF5IO::readFixFormatFile(){
    std::string line;
    ifstream fixFile(datFileName,std::ifstream::in);
    vector<string> vectorHold;
    stringstream ss;
    std::string stringhold,stringhold1;
    wholeList.clear();
    tableLength = 0;
    fieldLength = 0;
    int hold = 0;
    char firstLetter; 
    fileType = "FIX";
    fixFile.get(firstLetter);
    if (firstLetter == int('!') ) {
        std::getline(fixFile,headerLine);
    }else{
        headerLine = " ";
    }
    while(getline(fixFile,line)){
        /* cout << line << endl; */
        if (line.empty()) {
            vectorHold.clear();
            vectorHold.push_back("  ");
            wholeList.push_back(vectorHold);
        }else{
            ss.str(line);
            vectorHold.clear();
            hold = 0;
            ss >> stringhold;
            while(ss){
                hold = hold + 1;
                if (stringhold[0] == int('!')) {
                    std::getline(ss,stringhold1);
                    /* std::cout << "stringhold " << stringhold<<std::endl; */
                    /* std::cout << "stringhold1 " << stringhold1<<std::endl; */
                    stringhold = stringhold + stringhold1; 
                    ss.str("");
                    ss >> stringhold1;
                }
                vectorHold.push_back(stringhold);
                /* std::cout << tableLength <<" "<<stringhold << std::endl; */
                if (hold>fieldLength) {
                    fieldLength = hold;
                }
                ss >> stringhold;
            }
            wholeList.push_back(vectorHold);
            ss.str("");
            ss.clear();
        }
        tableLength =tableLength +1;
    }
    fixFile.close();
}


void TableHDF5IO::outputAuto(){
    /* fileType = trim(fileType); */
    /* cout << "file tyupe --------" << fileType<< "|" << endl; */
    if (fileType == "FIX"){
        outputFixFormatFile();
    }else if (fileType == "FREE"){
        outputFreeFormatFile();
    }else if (fileType == "TIME"){
        outputTimeDependentFile();
    }else if (fileType == "JSON"){
        stringSize = 256;
        outputJSONFile();
    }else{
        cout << "Un recognized file type "<< fileType << endl;
    }
}

void TableHDF5IO::outputFixFormatFile(){
    ofstream output;
    output.open(datFileName);
    if (headerLine != " ") {
        output << headerLine<< std::endl;
    }
    /* std::cout << "output for fix format" << std::endl; */
    for (int i = 0; i < wholeList.size(); i++) {
        for (int j = 0; j < wholeList[i].size(); j++) {
            output << wholeList[i][j] << " " ;
            /* std::cout << wholeList[i][j] << " " ; */
        }
        output << std::endl;
        /* std::cout << std::endl; */

    }       
    output.close();
 
}

void TableHDF5IO::readFreeFormatFile(){
    FreeFormatParser freeformat;
    freeformat.setFilename(datFileName);
    freeformat.parse();

    std::string line;
    ifstream freeFile(datFileName,std::ifstream::in);
    std::getline(freeFile,line);
    if (line[0] == int('#')) {
        headerLine=line;
    }
    freeFile.close();
    fileType = "FREE";

    int firstLength = freeformat.getFirstLevelLength();
    int secondLength =freeformat.getSecondLevelLength();
    vector<vector<string> > firstList = freeformat.getFirstWhole();
    vector<vector<string> > secondList = freeformat.getSecondWhole();
    tableLength = firstLength + secondLength;
    fieldLength = 3;
    wholeList.clear();
    vector<string> vectorHold(3);
    for (int i = 0; i < tableLength; i++) {
        vectorHold[0] = " ";
        vectorHold[1] = " ";
        vectorHold[2] = " ";
        wholeList.push_back(vectorHold);
        if (i < firstLength) {
           vectorHold[0]=firstList[i][0]; 
           vectorHold[1]=firstList[i][1]; 
           vectorHold[2]=" "+firstList[i][2]+" "; 
        }else{
            vectorHold[0]=secondList[i-firstLength][0]+"."+secondList[i-firstLength][1];
            vectorHold[1]=secondList[i-firstLength][2];
            vectorHold[2]=" "+secondList[i-firstLength][3]+" ";
        }
        wholeList[i]=vectorHold;
    }   
}

json TableHDF5IO::convertVec2JSON(vector<vector<std::string> > vec2,std::string parent,std::string listIndex){
    json output;
    for (int i = 0; i < vec2.size(); i++) {
        if (vec2[i][0] == parent && vec2[i][3] == listIndex) {
            if (vec2[i][2] == "String" ) {
                output.emplace(vec2[i][1], vec2[i][5]);
            }else if (vec2[i][2] == "Number") {
                output.emplace(vec2[i][1], std::stof(vec2[i][5]));
            }else if (vec2[i][2] == "Object") {
                output.emplace(vec2[i][1],convertVec2JSON(vec2,vec2[i][1],vec2[i][3]));
            }else if (vec2[i][2] == "List") {
                json array;
                for (int j = 0; j < std::stoi(vec2[i][4]); j++) { 
                    array.emplace_back(convertVec2JSON(vec2,vec2[i][1],std::to_string(j)));
                }
                output.emplace(vec2[i][1],array);
            }
        }
    }

    return output;
}

void TableHDF5IO::outputJSONFile(){
    std::ofstream o(datFileName);
    json j;
    j = convertVec2JSON(wholeList,"root"," ");
    /* cout << j.size() << std::endl; */
    o << std::setw(4) << j << std::endl;
    o.close();
}

void TableHDF5IO::outputFreeFormatFile(){
    ofstream output;
    output.open(datFileName);
    output << headerLine<< std::endl;
    for (int i = 0; i < tableLength; i++) {
            if (wholeList[i][2] != "" ) {
                output << wholeList[i][0] << " = " << wholeList[i][1] << std::endl;;
            }else{
                output << wholeList[i][0] << " = " << wholeList[i][1] << " # " << wholeList[i][2]<<std::endl;;
            }
    }       
    output.close();
 
}

void TableHDF5IO::outputTimeDependentFile(){
    ofstream output;
    output.open(datFileName);
    output << headerLine<< std::endl;
    for (int i = 0; i < wholeList.size(); i++) {
        for (int j = 0; j < wholeList[i].size(); j++) {
            output << wholeList[i][j] << " " ;
        }
        output << std::endl;
    }       
    output.close();

}

void TableHDF5IO::readTimeDependentFile(){
    std::string line;
    ifstream freeFile(datFileName,std::ifstream::in);
    std::getline(freeFile,headerLine);
    vector<string> vectorHold;
    stringstream ss;
    std::string stringhold;
    wholeList.clear();
    tableLength = 0;
    fieldLength = 0;
    int hold = 0;
    fileType = "TIME";
    while(getline(freeFile,line)){
        /* cout << line << endl; */
        ss.str(line);
        vectorHold.clear();
        hold = 0;
        ss >> stringhold;
        while(ss){
            hold = hold + 1;
            vectorHold.push_back(stringhold);
            /* std::cout << tableLength <<" "<<stringhold << std::endl; */
            if (hold>fieldLength) {
                fieldLength = hold;
            }
            ss >> stringhold;
        }
        wholeList.push_back(vectorHold);
        ss.str("");
        ss.clear();
        tableLength =tableLength +1;
    }
    freeFile.close();
}

//std::string TableHDF5IO::trim(std::string str){
//    size_t first=str.find_first_not_of(' ');
//    if (string::npos == first) {
//        return str;
//    }
//    size_t last = str.find_last_not_of(' ');
//    return str.substr(first,(last-first+1));
//}

void TableHDF5IO::readH5File(std::string groupName){
     hid_t file_id,group_id,dataset_id,dataspace_id,plist_id,string_type,string_type1024,attribute_id,dapl_id,chunkds_id;
    herr_t status;
    std::string wholeGroupName;
    std::string wholeDataName;
    vector<std::string> vectorHold;
//    if (groupName[0] == '/') {
//        wholeGroupName = groupName;
//    }else{
//        wholeGroupName = '/'+groupName;
//    }
    wholeGroupName = getTrueGroupName(groupName);
    wholeDataName = wholeGroupName + '/' + datFileName;
//    std::ifstream ifile(h5FileName.c_str());
//    if (ifile) {
//        file_id = H5Fopen(h5FileName.c_str(),H5F_ACC_RDWR,H5P_DEFAULT);
//    }else{
//        std::cout << "Error, the file does not exists" << std::endl;
//    }
    file_id = openH5File(false);
    group_id = openH5Group(wholeGroupName,false);
//    if (groupName != "" ) {
//        status = H5Gget_objinfo(file_id,wholeGroupName.c_str(), 0, NULL);
//        if (status == 0) {
//            group_id = H5Gopen(file_id,wholeGroupName.c_str(),0); 
//        }else{
//            std::cout << "Error, the group name does not exist" << std::endl;
//        }
//    }
//   if (groupName != "") {
//       dataset_id = H5Dopen(group_id,datFileName.c_str(),H5P_DEFAULT);
//   }else{
//       dataset_id = H5Dopen(file_id,datFileName.c_str(),H5P_DEFAULT);
//   }


    dataset_id = H5Dopen(group_id,datFileName.c_str(),H5P_DEFAULT);

    fileType = readStrAttribute(dataset_id,"File Type");

    if (fileType=="JSON") {
        stringSize = 256;
    }
    plist_id = H5Dget_create_plist(dataset_id);
    string_type = H5Tcopy(H5T_C_S1);
    H5Tset_size( string_type, stringSize);


    dataspace_id = H5Dget_space(dataset_id);
    const int ndims = H5Sget_simple_extent_ndims(dataspace_id);
    hsize_t dims[ndims],cdims[ndims],start[ndims],count[ndims];
    H5Sget_simple_extent_dims(dataspace_id,dims,NULL);
    /* std::cout << "ndims " << ndims << " " << dims << std::endl; */ 
    fieldLength = dims[1];
    tableLength = dims[0];
    dapl_id = H5Pcreate(H5P_DATASET_ACCESS);
    cdims[0] = chunkSize;
    cdims[1] = fieldLength;
    start[0]=0;start[1]=0;
    count[0]=chunkSize;count[1]=fieldLength;

    char dataHold[chunkSize][fieldLength][stringSize];
    chunkds_id = H5Screate_simple(ndims,cdims,NULL);
    status = H5Pset_chunk_cache(dapl_id,H5D_CHUNK_CACHE_NSLOTS_DEFAULT,128*1024*1024,H5D_CHUNK_CACHE_W0_DEFAULT);
    for (int xStart = 0; xStart < tableLength; xStart=xStart+chunkSize) {
       start[0]=xStart; 
       status = H5Sselect_hyperslab(dataspace_id,H5S_SELECT_SET,start,NULL,count,NULL);
       status = H5Dread(dataset_id,string_type,chunkds_id,dataspace_id,H5P_DEFAULT,dataHold);
    std::string stringhold;
    for (int i = 0; i < chunkSize; i++) {
        for (int j = 0; j < fieldLength; j++) {
            stringhold=trim(dataHold[i][j]);
            vectorHold.push_back(stringhold);
            /* std::cout << tableLength << " " << fieldLength << " " << i << " " << j << " "<< dataHold[i][j] << std::endl; */
        }
            wholeList.push_back(vectorHold);
        vectorHold.clear();
    }

    }

    headerLine = readStrAttribute(dataset_id,"Header");
//    char attributeHold[1024];
//    string_type1024 = H5Tcopy(H5T_C_S1);
//    H5Tset_size( string_type1024, 1024); 
//    attribute_id = H5Aopen(dataset_id,"Header",H5P_DEFAULT);
//    status = H5Aread(attribute_id,string_type1024,&attributeHold);
//    headerLine = attributeHold;
//    H5Aclose(attribute_id);
//
    /* cout << "file type fro read " << fileType << endl; */

//    attribute_id = H5Aopen(dataset_id,"File Type",H5P_DEFAULT);
//    status = H5Aread(attribute_id,string_type1024,&attributeHold);
//    fileType = trim(attributeHold);
//    H5Aclose(attribute_id);



    /* cout << "headerline" << headerLine << endl; */
  
    H5Dclose(dataset_id);
    H5Sclose(dataspace_id);
    H5FGclose();
    /* H5Gclose(group_id); */
    /* H5Fclose(file_id); */
   
}

void TableHDF5IO::setChunkSize(int size){
    chunkSize = size;
}


void TableHDF5IO::outputH5(std::string groupName){
    hid_t file_id,group_id,dataset_id,dataspace_id,attribute_id,att_dataspace,plist_id,dapl_id,chunkds_id;
    hid_t string_type,string_type1024;
    herr_t status;
    std::string wholeGroupName;
    std::string wholeDataName;
    /* wholeGroupName = '/'+groupName; */
    wholeGroupName = getTrueGroupName(groupName);
    wholeDataName = wholeGroupName + '/' + datFileName;
    /* std::ifstream ifile(h5FileName.c_str()); */
//    if (ifile) {
//        file_id = H5Fopen(h5FileName.c_str(),H5F_ACC_RDWR,H5P_DEFAULT);
//    }else{
//            /* std::cout << "create the filep" << std::endl; */
//        file_id = H5Fcreate(h5FileName.c_str(),H5F_ACC_TRUNC,H5P_DEFAULT,H5P_DEFAULT);
//    }
//    if (groupName != "" ) {
//        status = H5Gget_objinfo(file_id,wholeGroupName.c_str(), 0, NULL);
//        if (status == 0) {
//            group_id = H5Gopen(file_id,wholeGroupName.c_str(),0); 
//        }else{
//            /* std::cout << "create the gourp " << wholeGroupName.c_str() << std::endl; */
//            group_id = H5Gcreate(file_id,wholeGroupName.c_str(),H5P_DEFAULT,H5P_DEFAULT,H5P_DEFAULT);
//        }
//
//    }

    file_id = openH5File(true);
    /* group_id = openH5Group(wholeGroupName,true); */
    group_id = openH5Group(groupName,true);

            /* std::cout << "create the gourp " << wholeGroupName.c_str() << std::endl; */
    hsize_t dims[2],cdims[2],start[2],count[2];
    dims[1] = fieldLength;
    dims[0] = tableLength;
    cdims[0] = chunkSize;
    cdims[1] = fieldLength;
    dataspace_id = H5Screate_simple(2,dims, NULL);
    string_type = H5Tcopy(H5T_C_S1);
    H5Tset_size( string_type, stringSize);
//    string_type1024 = H5Tcopy(H5T_C_S1);
//    H5Tset_size( string_type1024, 1024);
   // StrType strtype(PredType::C_S1,256);
    plist_id = H5Pcreate(H5P_DATASET_CREATE);
    dapl_id = H5Pcreate(H5P_DATASET_ACCESS);
    status = H5Pset_chunk(plist_id,2,cdims);
    status = H5Pset_deflate(plist_id,9);
    status = H5Pset_chunk_cache(dapl_id,H5D_CHUNK_CACHE_NSLOTS_DEFAULT,1024*1024*128,H5D_CHUNK_CACHE_W0_DEFAULT);

//    if (groupName != "") {
//        dataset_id = H5Dcreate(group_id,datFileName.c_str(),string_type64,dataspace_id,H5P_DEFAULT,plist_id,H5P_DEFAULT);
//    }else{
//        dataset_id = H5Dcreate(file_id,datFileName.c_str(),string_type64,dataspace_id,H5P_DEFAULT,plist_id,H5P_DEFAULT);
//    }
//
    dataset_id = H5Dcreate(group_id,datFileName.c_str(),string_type,dataspace_id,H5P_DEFAULT,plist_id,dapl_id);
    /* std::cout << "dize of datahold" << sizeof(char)*tableLength*fieldLength*64/1024/1024 << endl; */ 
    char dataHold[chunkSize][fieldLength][stringSize] ;
    /* std:: cout << "after the datahold" << endl; */

    start[0]=0;start[1]=0;
    count[0]=chunkSize,count[1]=fieldLength;
    chunkds_id = H5Screate_simple(2,cdims,NULL);
    for (int xStart = 0; xStart < tableLength; xStart=xStart+chunkSize) {
        
    for (int i = 0; i < chunkSize; i++) {
        for (int j = 0; j < fieldLength; j++) {
            /* dataHold[i][j] = (char*)malloc(64*sizeof(char)); */
            strcpy(dataHold[i][j]," ");
            if (j<wholeList[i+xStart].size()) {
                    strcpy(dataHold[i][j],wholeList[i+xStart][j].c_str());
            }
            /* std::cout << tableLength << " " << fieldLength << " " << i << " " << j << " "<< dataHold[i][j] << std::endl; */
        }
    }

    /* std::cout << "during the write phase " << xStart << endl; */
    /* std::cout << sizeof(dataHold[0][0]) << " " <<sizeof(dataHold)<<std::endl; */
    start[0] = xStart;
        status = H5Sselect_hyperslab(dataspace_id,H5S_SELECT_SET,start,NULL,count,NULL);
    status = H5Dwrite(dataset_id,string_type,chunkds_id,dataspace_id,H5P_DEFAULT,dataHold);

    }
    /* std::cout << "after the write phase" << endl; */

    writeStrAttribute(dataset_id,"Header",headerLine);
    writeStrAttribute(dataset_id,"File Type",fileType);

//    char attributeHold[1024];
//    strcpy(attributeHold,headerLine.c_str());
//    /* std::cout << "headerline" << headerLine.c_str() << std::endl; */
//    /* std::cout << "headerline" << attributeHold << std::endl; */
//    att_dataspace = H5Screate(H5S_SCALAR);
//    attribute_id = H5Acreate(dataset_id,"Header",string_type1024,att_dataspace,H5P_DEFAULT,H5P_DEFAULT);
//    /* std::cout << "after the crate" << std::endl; */
//    status = H5Awrite(attribute_id,string_type1024,&attributeHold);
//    /* std::cout << "after the write of attr" << std::endl; */
//
//    H5Aclose(attribute_id);
//
//    strcpy(attributeHold,fileType.c_str());
//    /* std::cout << "headerline" << headerLine.c_str() << std::endl; */
//    /* std::cout << "headerline" << attributeHold << std::endl; */
//    att_dataspace = H5Screate(H5S_SCALAR);
//    attribute_id = H5Acreate(dataset_id,"File Type",string_type1024,att_dataspace,H5P_DEFAULT,H5P_DEFAULT);
//    /* std::cout << "after the crate" << std::endl; */
//    status = H5Awrite(attribute_id,string_type1024,&attributeHold);
//    /* std::cout << "after the write of attr" << std::endl; */
//
//    H5Aclose(attribute_id);

    H5Dclose(dataset_id);
    H5Sclose(dataspace_id);
    /* H5Sclose(att_dataspace); */
    /* H5Gclose(group_id); */
    /* H5Fclose(file_id); */
    H5FGclose();
}

//void TableHDF5IO::output2H5(std::string groupName,std::string tableTitle){
//    hid_t file_id,group_id,dataset_id,dataspace_id,attr_id;
//    hid_t field_type[2],string_type256,string_type2048;
//    herr_t status;
//    int i;
//    std::string wholeGroupName;
//    std::string wholeDataName;
//    wholeGroupName = '/'+groupName;
//    wholeDataName = wholeGroupName + '/' + datFileName;
//    std::ifstream ifile(h5FileName.c_str());
//    if (ifile) {
//        file_id = H5Fopen(h5FileName.c_str(),H5F_ACC_RDWR,H5P_DEFAULT);
//    }else{
//        file_id = H5Fcreate(h5FileName.c_str(),H5F_ACC_TRUNC,H5P_DEFAULT,H5P_DEFAULT);
//    }
//
//    if (groupName != "" ) {
//        status = H5Gget_objinfo(file_id,wholeGroupName.c_str(), 0, NULL);
//        if (status == 0) {
//            group_id = H5Gopen(file_id,wholeGroupName.c_str(),0); 
//        }else{
//            group_id = H5Gcreate(file_id,wholeGroupName.c_str(),H5P_DEFAULT,H5P_DEFAULT,H5P_DEFAULT);
//        }
//    }
//
//    tableline table_data[tableLength];
//
//    std::cout << "before the table data" << sizeof(table_data) << " " << tableLength<<std::endl;
//    for (int i = 0; i < tableLength; i++) {
//            strcpy(table_data[i].name,wholeList[i][0].c_str());
//            strcpy(table_data[i].value,wholeList[i][1].c_str());
//            strcpy(table_data[i].comment,wholeList[i][2].c_str());
//        std::cout << "copy" << i << table_data[i].name << std::endl;
//    }
//    std::cout << "after the table data" << table_data[0].name <<std::endl;
//    size_t dst_size = sizeof(tableline);
//    size_t dst_offset[3] = {HOFFSET( tableline, name),
//                            HOFFSET( tableline, value),
//                            HOFFSET( tableline, comment)};
//    size_t dst_sizes[3] = {sizeof(table_data[0].name),
//                            sizeof(table_data[0].value),
//                            sizeof(table_data[0].comment)};
//    const char *field_names[3]={"Name","Value","Comment"};
//    hsize_t chunk_size = 10;
//    int *fill_data = NULL;
//    int compress = 0;
//
//    string_type256 = H5Tcopy(H5T_C_S1);
//    H5Tset_size( string_type256, 256);
//    string_type2048 = H5Tcopy(H5T_C_S1);
//    H5Tset_size( string_type2048, 2048);
//
//    attr_id = H5Acreate()
//
//    field_type[0] = string_type256;
//    field_type[1] = string_type2048;
//    field_type[2] = string_type256;
//    std::cout << "error int hte write" << table_data[0].name <<std::endl;
//    if (groupName != "") {
//        H5TBmake_table(tableTitle.c_str(),group_id,datFileName.c_str(),3,tableLength,dst_size,field_names,dst_offset,field_type,chunk_size,fill_data,compress,table_data);
//    }else{
//        H5TBmake_table(tableTitle.c_str(),file_id,datFileName.c_str(),3,tableLength,dst_size,field_names,dst_offset,field_type,chunk_size,fill_data,compress,table_data);
//    }
//
//
//    H5Gclose(group_id);
//    H5Fclose(file_id);
//}
