#include <MuDataset.h>

#define VTK_CREATE(type,name) \
    vtkSmartPointer<type> name = vtkSmartPointer<type>::New()

using namespace std;

MuDataset::MuDataset(){}
MuDataset::MuDataset(string str){
    datFileName=str;
}
MuDataset::~MuDataset(){}

int * MuDataset::getDimension(int dim[4]){
    dim[0]=x;
    dim[1]=y;
    dim[2]=z;
    dim[3]=col;
    return dim;
}

double **** MuDataset::getData(){
    return data;
}

void MuDataset::setDimension(int xIn,int yIn,int zIn, int colIn){
    x=xIn;
    y=yIn;
    z=zIn;
    col=colIn;
}

void MuDataset::setDatFileName(string str){

    datFileName=str;

    fileName=datFileName.substr(0,datFileName.find("."));

    string filename;
    filename=datFileName.substr(0, datFileName.find_last_of("."));
    vtkFileName=filename+".vtk";
    vtiFileName=filename+".vti";


    /* cout << "The data file name is: " << datFileName << endl; */
}

string MuDataset::getDatFileName(){
    return datFileName;
}

string MuDataset::getVTKFileName(){
    return vtkFileName;
}

string MuDataset::getVTIFileName(){
    return vtiFileName;
}

void MuDataset::setVTKFileName(string str){
    vtkFileName=str;

    /* cout  << "The vtk file name is: " << vtkFileName << endl; */
}

void MuDataset::setVTIFileName(string str){
    vtiFileName=str;

    /* cout  << "The vti file name is: " << vtiFileName << endl; */
}

void MuDataset::readDatFile(){
    ifstream input;
    string line;
    int xhold=0,yhold=0,zhold=0,columnCount=0;
    double hold=0;
    input.open(datFileName);
    // Read the first line to get x,y,z
    getline(input,line);
    istringstream iss(line);
    iss >> x >> y >> z;
    // Read the second line to get the column number
    getline(input,line);
    iss.str(line);
    while (iss >> hold){
        columnCount++;
    }
    col=columnCount-3;
    input.close();


    // Initialize the data array
    data=new double***[col];
    for (int i = 0; i < col; i++) {
        data[i]=new double**[x];
        for (int j = 0; j < x; j++) {
            data[i][j]=new double*[y];
            for (int k = 0; k < y; k++) {
                data[i][j][k]=new double[z];
            }
        }
    }



    // Reopen the file, and this time we'll read the data
    input.open(datFileName);
    // Skip the first line
    getline(input,line);

    // Fill in the data
    for (int i = 0; i < x; i++) {
        for (int j = 0; j < y; j++) {
             for (int k = 0; k < z; k++) {
                getline(input,line);
                /* cout << "This is the line:" <<line<<endl; */
                iss.clear();
                iss.str(line);
                /* cout << "This is the line:" <<iss.str()<<endl; */
                iss >> xhold >> yhold >> zhold;
                iss >> std::scientific;
                /* cout << "ijk:"<<i <<" "<<j << " " <<k << " "; */
                /* cout << "ijk:"<<xhold <<" "<<yhold << " " <<zhold << " "; */
                for (int m = 0; m < col; m++) {
                    iss >> hold;
                    data[m][i][j][k]=hold;
                    /* cout << data[i][j][k][m] <<" "<<hold<<" "; */
                }
                /* cout << endl; */
             }
        }
    }   

    input.close();
}

void MuDataset:: outputVTKFile(){
    ofstream output;


    output.open(vtkFileName);
    output << "# vtk DataFile Version 3.0\n";
    output << "Structured Points\n";
    output << "ASCII\n";
    output << "\n";
    output << "DATASET STRUCTURED_POINTS\n";
    output << "DIMENSIONS " << std::to_string(x) << " " << std::to_string(y) <<" "<< std::to_string(z) << "\n";
    output << "ORIGIN 0 0 0\n";
    output << "SPACING " << 1 << " " << 1 << " " << 1 << "\n";
    output << "\n";
    output << "POINT_DATA " << std::to_string(x*y*z)+"\n";

    for (int m = 0; m < col; m++) {

        output << "SCALARS " << fileName << "_" << to_string(m) << " float\n";
        output << "LOOKUP_TABLE default\n";
        output << std::scientific;

        for (int i = 0; i < x; i++) {
            for (int j = 0; j < y; j++) {
                for (int k = 0; k < z; k++) {
                    output << data[m][i][j][k] << endl;; 
                }
            }
        }   

        output << endl;

    }


    output.close();

    

}

void MuDataset::outputVTIFile(){

    VTK_CREATE(vtkImageData,imageData);
    imageData->SetDimensions(x,y,z);
    VTK_CREATE(vtkDoubleArray,imageDataHold[col]);
    /* imageDataHold[m]->AllocateScalars(VTK_DOUBLE,1); */
    string tempName;
    for (int m = 0; m < col; m++) {
        imageDataHold[m]->SetNumberOfComponents(1);
        imageDataHold[m]->SetNumberOfTuples(x*y*z);
        tempName=fileName+"_"+to_string(m);
        imageDataHold[m]->SetName(tempName.c_str());


        for (int i = 0; i < x; i++) {
            for (int j = 0; j < y; j++) {
                for (int k = 0; k < z; k++) {
                    imageDataHold[m]->SetValue(i+j*x+k*x*y,data[m][i][j][k]);
                }
            }
        }   

        imageData->GetPointData()->AddArray(imageDataHold[m]);

    }
    /* imageData->GetPointData()->SetScalars() */
    /* int *dims=imageData->GetDimensions(); */

    VTK_CREATE(vtkXMLImageDataWriter,writer);
    writer->SetFileName(vtiFileName.c_str());
    writer->SetInputData(imageData);
    writer->Write();


}

void MuDataset::outputDomainVTIFile(FerroDomain ferroDomain){
    VTK_CREATE(vtkImageData,imageData);
    imageData->SetDimensions(x,y,z);
    VTK_CREATE(vtkDoubleArray,imageDataHold[col/3]);
    VTK_CREATE(vtkDoubleArray,imageDomainType);
    string tempName;
    int domainNum;


    imageDomainType->SetNumberOfComponents(1);
    imageDomainType->SetNumberOfTuples(x*y*z);
    tempName="domain";
    imageDomainType->SetName(tempName.c_str());
    for (int i = 0; i < x; i++) {
        for(int j = 0; j < y; j++){
            for (int k = 0; k < z; k++) {
                domainNum=ferroDomain.getDomainType(data[0][i][j][k],data[1][i][j][k],data[2][i][j][k]);
                imageDomainType->SetTuple1(i+j*x+k*x*y,domainNum);

            }
        }
    }
    imageData->GetPointData()->AddArray(imageDomainType);



    for(int m=0;m<col/3;m++){
        imageDataHold[m]->SetNumberOfComponents(3);
        imageDataHold[m]->SetNumberOfTuples(x*y*z);
        tempName="vector_"+to_string(m);
        imageDataHold[m]->SetName(tempName.c_str());

        for (int i = 0; i < x; i++) {
            for(int j = 0; j < y; j++){
                for (int k = 0; k < z; k++) {
                    imageDataHold[m]->SetTuple3(i+j*x+k*x*y,data[m][i][j][k],data[m+1][i][j][k],data[m+2][i][j][k]);

                }
            }
        }
        imageData->GetPointData()->AddArray(imageDataHold[m]);
    }

        VTK_CREATE(vtkXMLImageDataWriter,writer);
    writer->SetFileName(vtiFileName.c_str());
    writer->SetInputData(imageData);
    writer->Write();
}

