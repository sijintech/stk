#include <DataHDF5IO.h>
/* using namespace H5; */

DataHDF5IO::DataHDF5IO(){
    x=0;y=0;z=0;col=0;chunkX=1;
}
DataHDF5IO::~DataHDF5IO(){}

//void DataHDF5IO::setDatFileName(std::string datFile){
//    datFileName = datFile;
//}
//
//void DataHDF5IO::setH5FileName(std::string h5File){
//    h5FileName = h5File;
//}

void DataHDF5IO::setChunkX(int chunk){
    chunkX = chunk;
}

void DataHDF5IO::cleanDat(){
    clear();
    for (int i = 0; i < col; i++) {
        for (int j = 0; j < chunkX; j++) {
            for (int k = 0; k < y; k++) {
                delete [] data[i][j][k];
            }
            delete [] data[i][j];
        }
        delete [] data[i];
    }
    delete [] data;   

    x=0;y=0;z=0;col=0;chunkX=1;
}

void DataHDF5IO::readDat(bool header,bool finish){
    /* ifstream input; */
    string line;
    int xhold=0,yhold=0,zhold=0,columnCount=0;
    double hold=0;
    istringstream iss;

//    if (header) {
//        input.open(datFileName);
//        // Read the first line to get x,y,z
//        getline(input,line);
//        iss.str(line);
//        iss >> x >> y >> z;
//        iss.clear();
//        getline(input,line);
//        iss.str(line);
//        iss >> hold >> hold >> hold;
//        col = 0;
//        while (iss >> hold){
//            col++;
//        }
//        input.close();
//
//
//    }
//
//    // Initialize the data array
//    data=new double***[col];
//    for (int i = 0; i < col; i++) {
//        data[i]=new double**[chunkX];
//        for (int j = 0; j < x; j++) {
//            data[i][j]=new double*[y];
//            for (int k = 0; k < y; k++) {
//                data[i][j][k]=new double[z];
//            }
//        }
//    }

    /* cout << "after the data allocate" << endl; */



    // Reopen the file, and this time we'll read the data
    if (header) {
        input.open(datFileName);
        // Skip the first line
        getline(input,line);

    }
    vector<double> minHold(col);
    vector<double> maxHold(col);
    // Fill in the data
    for (int i = 0; i < chunkX; i++) {
        for (int j = 0; j < y; j++) {
             for (int k = 0; k < z; k++) {
                getline(input,line);
                iss.clear();
                iss.str(line);
                iss >> xhold >> yhold >> zhold;
                iss >> std::scientific;
                for (int m = 0; m < col; m++) {
                    iss >> hold;
                    data[m][i][j][k]=hold;
                }
             }
        }
    }   

    if (finish) {
        input.close();
    }

}

void DataHDF5IO::readH5writeDat(std::string groupName){
    hid_t file_id,group_id,dataset_id,dataspace_id,plist_id,dapl_id,chunkds_id;
    herr_t status;
    std::string wholeGroupName;
    std::string wholeDataName;
    bool header,finish;
    wholeGroupName = getTrueGroupName(groupName);
    wholeDataName = wholeGroupName + '/' + datFileName;
   
    file_id = openH5File(false);
    group_id = openH5Group(wholeGroupName,false);     
    dataset_id = H5Dopen(group_id,datFileName.c_str(),H5P_DEFAULT);

    /* plist_id = H5Dget_create_plist(dataset_id); */


    dataspace_id = H5Dget_space(dataset_id);
    const int ndims = H5Sget_simple_extent_ndims(dataspace_id);
    /* hsize_t dims[ndims]; */
    hsize_t dims[4],cdims[4],start[4],count[4],stride[4],block[4];
    H5Sget_simple_extent_dims(dataspace_id,dims,NULL);
    /* std::cout << "ndims " << ndims << " " << dims << std::endl; */ 
    x = dims[1];
    y = dims[2];
    z = dims[3];
    col = dims[0];

    /* plist_id = H5Pcreate(H5P_DATASET_CREATE); */
    dapl_id = H5Pcreate(H5P_DATASET_ACCESS);
    cdims[0] = col;
    cdims[1] = chunkX;
    cdims[2] = y;
    cdims[3] = z;
    /* status = H5Pset_chunk(plist_id,4,cdims); */
    /* status = H5Pset_deflate(plist_id,9); */
            /* std::cout << "create the gourp " << x << y << z << col << std::endl; */

    status = H5Pset_chunk_cache(dapl_id,H5D_CHUNK_CACHE_NSLOTS_DEFAULT,128*1024*1024,H5D_CHUNK_CACHE_W0_DEFAULT);

    double dataHold[col][chunkX][y][z];
    start[0]=0;start[1]=0;start[2]=0;start[3]=0;
    count[0]=col;count[1]=chunkX;count[2]=y;count[3]=z;

    data=new double***[col];
    for (int i = 0; i < col; i++) {
        data[i]=new double**[chunkX];
        for (int j = 0; j < chunkX; j++) {
            data[i][j]=new double*[y];
            for (int k = 0; k < y; k++) {
                data[i][j][k]=new double[z];
            }
        }
    }



    chunkds_id = H5Screate_simple(4,cdims, NULL);
    for (int xStart = 0; xStart < x; xStart=xStart+chunkX) {
 

    start[1] = xStart;

                    /* std::cout << "to select "  << xStart<< std::endl; */
    status = H5Sselect_hyperslab(dataspace_id,H5S_SELECT_SET,start,NULL,count,NULL);

                    /* std::cout << "to write" << std::endl; */
 


    /* std::cout << "dims " << x << " " << y << " " << z << " " << col << std::endl; */ 
    /* status = H5Dread(dataset_id,H5T_NATIVE_DOUBLE,H5S_ALL,H5S_ALL,H5P_DEFAULT,dataHold); */
    status = H5Dread(dataset_id,H5T_NATIVE_DOUBLE,chunkds_id,dataspace_id,H5P_DEFAULT,dataHold);
    /* std::cout << "data " << sizeof(dataHold[0][0][0]) << " " << dataHold[0][0][0][0] << std::endl; */ 
    for (int i = 0; i < col; i++) {
        for (int j = 0; j < chunkX; j++) {
            for (int k = 0; k < y; k++) {
                for (int l = 0; l < z; l++) {
                    data[i][j][k][l] = dataHold[i][j][k][l];
                }
            }
        }
    }


    if (xStart==0) {
        header=true;
    }else{
        header=false;
    }

    if (xStart+chunkX >= x) {
        finish = true;
    }else{
        finish = false;
    }
    /* cout << "before output " << header << finish << endl; */
    outputDat(header,finish,xStart);
    /* cout << "after output " << xStart << endl; */
}

    /* std::cout << "data " << sizeof(data[0][0][0]) << " " << data[0][0][0][0]  << std::endl; */ 
    
    H5Dclose(dataset_id);
    H5Sclose(dataspace_id);
    /* H5Gclose(group_id); */
    /* H5Fclose(file_id); */
    H5FGclose();
   
}



void DataHDF5IO::readDatwriteH5(std::string groupName){
    hid_t file_id,group_id,dataset_id,dataspace_id,plist_id,dapl_id,chunkds_id;
    herr_t status;
    std::string wholeGroupName,line,hold;
    std::string wholeDataName;
    bool header,finish;
    /* wholeGroupName = '/'+groupName; */
    wholeGroupName = getTrueGroupName(groupName);
    wholeDataName = wholeGroupName + '/' + datFileName;
    std::ifstream ifile(h5FileName.c_str());
    istringstream iss;
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
            /* std::cout << "create the gourp " << wholeGroupName.c_str() << std::endl; */

        input.open(datFileName);
        // Read the first line to get x,y,z
        getline(input,line);
        iss.str(line);
        iss >> x >> y >> z;
        iss.clear();
        getline(input,line);
        iss.str(line);
        iss >> hold >> hold >> hold;
        col = 0;
        while (iss >> hold){
            col++;
        }
        input.close();



        /* cout << "allocate"<<x<<y<<z<<col<<chunkX << endl; */
    // Initialize the data array
    data=new double***[col];
    for (int i = 0; i < col; i++) {
        data[i]=new double**[chunkX];
        for (int j = 0; j < chunkX; j++) {
            data[i][j]=new double*[y];
            for (int k = 0; k < y; k++) {
                data[i][j][k]=new double[z];
            }
        }
    }



        /* cout << "allocate"<<x<<y<<z<<col<<chunkX << endl; */





    file_id = openH5File(true);
    group_id = openH5Group(groupName,true);
    hsize_t dims[4],cdims[4],start[4],count[4],stride[4],block[4];
    dims[1] = x;
    dims[2] = y;
    dims[3] = z;
    dims[0] = col;
    dataspace_id = H5Screate_simple(4,dims, NULL);
    plist_id = H5Pcreate(H5P_DATASET_CREATE);
    dapl_id = H5Pcreate(H5P_DATASET_ACCESS);
    cdims[0] = col;
    cdims[1] = chunkX;
    cdims[2] = y;
    cdims[3] = z;
    status = H5Pset_chunk(plist_id,4,cdims);
    status = H5Pset_deflate(plist_id,9);
            /* std::cout << "create the gourp " << chunkX << x << y << z << col << std::endl; */

    status = H5Pset_chunk_cache(dapl_id,H5D_CHUNK_CACHE_NSLOTS_DEFAULT,128*1024*1024,H5D_CHUNK_CACHE_W0_DEFAULT);
//    if (groupName != "") {
//        dataset_id = H5Dcreate(group_id,datFileName.c_str(),H5T_NATIVE_DOUBLE,dataspace_id,H5P_DEFAULT,plist_id,dapl_id);
//    }else{
//        dataset_id = H5Dcreate(file_id,datFileName.c_str(),H5T_NATIVE_DOUBLE,dataspace_id,H5P_DEFAULT,plist_id,dapl_id);
//    }

            /* std::cout << "create the gourp " << chunkX << x << y << z << col << std::endl; */
    
    dataset_id = H5Dcreate(group_id,datFileName.c_str(),H5T_NATIVE_DOUBLE,dataspace_id,H5P_DEFAULT,plist_id,dapl_id);
            /* std::cout << "create the gourp " << data[0][0][0][0] << data[1][0][0][0]<< std::endl; */
            /* std::cout << "create the gourp " << chunkX << x << y << z << col << std::endl; */
    double dataHold[col][chunkX][y][z];
    start[0]=0;start[1]=0;start[2]=0;start[3]=0;
    count[0]=col;count[1]=chunkX;count[2]=y;count[3]=z;
            /* std::cout << "create the gourp " << chunkX << x << y << z << col << std::endl; */

    chunkds_id = H5Screate_simple(4,cdims, NULL);
    for (int xStart = 0; xStart < x; xStart=xStart+chunkX) {
        
                    /* std::cout << xStart << std::endl; */
    if (xStart==0) {
        header = true;
    }else{
        header = false;
    }
    if (xStart + chunkX >= x) {
        finish = true;
    }else{
        finish = false; 
    }
    readDat(header,finish);
    for (int i = 0; i < col; i++) {
        for (int j = 0; j < chunkX; j++) {
            for (int k = 0; k < y; k++) {
                for (int l = 0; l < z; l++) {
                    dataHold[i][j][k][l] = data[i][j][k][l];
                }
            }
        }
    }



    start[1] = xStart;

                    /* std::cout << "to select" << std::endl; */
    status = H5Sselect_hyperslab(dataspace_id,H5S_SELECT_SET,start,NULL,count,NULL);

                    /* std::cout << "to write" << std::endl; */
    status = H5Dwrite(dataset_id,H5T_NATIVE_DOUBLE,chunkds_id,dataspace_id,H5P_DEFAULT,dataHold);
                    /* std::cout << "after write" << std::endl; */

    }
    /* cout << "after loop" << endl; */
    fileType = "DAT";
    writeStrAttribute(dataset_id,"File Type",fileType);
    /* cout << "after loop" << endl; */
    H5Sclose(dataspace_id);
    /* cout << "after loop" << endl; */
    H5Dclose(dataset_id);
    /* cout << "after loop" << endl; */
    /* H5Gclose(group_id); */
    /* H5Pclose(plist_id); */
    /* H5Fclose(file_id); */
    H5FGclose();
    /* cout << "after loop" << endl; */
}

void DataHDF5IO::outputDat(bool header,bool finish,int base){
    /* ofstream output; */
    /* std::cout << datFileName.c_str() << x << y << z << col << std::endl; */
    if (header) {
        output.open(datFileName);
        output << setw(6) << x << setw(6) << y << setw(6) << z << std::endl;
    }
    for (int i = 0; i < chunkX; i++) {
        for (int j = 0; j < y; j++) {
            for (int k = 0; k < z; k++) {
                output << setw(6) << i+base+1 <<setw(6)<< j+1 <<setw(6)<< k+1;
                for (int l = 0; l < col; l++) {
                    /* std::cout << i << " " << j << " " << k << " " << l << " " << sizeof(data) << " " << sizeof(double) << std::endl; */
                    output << std::scientific << setw(16) << data[l][i][j][k] ;
                }
                output << std::endl;
                
            }   
        }
    }       
    if (finish) {
        output.close();
    }
    
}
