#include <VectorDomainDataset.h>
#include <vtkIntArray.h>

#define VTK_CREATE(type,name) \
    vtkSmartPointer<type> name = vtkSmartPointer<type>::New()

using namespace std;

VectorDomainDataset::VectorDomainDataset(){
    outputDomainAnalysis=false;
}
VectorDomainDataset::VectorDomainDataset(string str):Dataset(str){
}
VectorDomainDataset::~VectorDomainDataset(){}
//
//int * DomainDataset::getDimension(int dim[4]){
//    dim[0]=x;
//    dim[1]=y;
//    dim[2]=z;
//    dim[3]=col;
//    return dim;
//}
//
//double **** DomainDataset::getData(){
//    return data;
//}
//
//void DomainDataset::setDimension(int xIn,int yIn,int zIn, int colIn){
//    x=xIn;
//    y=yIn;
//    z=zIn;
//    col=colIn;
//}
//
//void DomainDataset::setDatFileName(string str){
//
//    datFileName=str;
//
//    fileName=datFileName.substr(0,datFileName.find("."));
//
//    string filename;
//    filename=datFileName.substr(0, datFileName.find_last_of("."));
//    vtkFileName=filename+".vtk";
//    vtiFileName=filename+".vti";
//
//
//    cout << "The data file name is: " << datFileName << endl;
//}
//
//string MuDataset::getDatFileName(){
//    return datFileName;
//}
//
//string MuDataset::getVTKFileName(){
//    return vtkFileName;
//}
//
//string MuDataset::getVTIFileName(){
//    return vtiFileName;
//}
//
//void MuDataset::setVTKFileName(string str){
//    vtkFileName=str;
//
//    cout  << "The vtk file name is: " << vtkFileName << endl;
//}
//
//void MuDataset::setVTIFileName(string str){
//    vtiFileName=str;
//
//    cout  << "The vti file name is: " << vtiFileName << endl;
//}
//
//void MuDataset::readDatFile(){
//    ifstream input;
//    string line;
//    int xhold=0,yhold=0,zhold=0,columnCount=0;
//    double hold=0;
//    input.open(datFileName);
//    // Read the first line to get x,y,z
//    getline(input,line);
//    istringstream iss(line);
//    iss >> x >> y >> z;
//    // Read the second line to get the column number
//    getline(input,line);
//    iss.str(line);
//    while (iss >> hold){
//        columnCount++;
//    }
//    col=columnCount-3;
//    input.close();
//
//
//    // Initialize the data array
//    data=new double***[col];
//    for (int i = 0; i < col; i++) {
//        data[i]=new double**[x];
//        for (int j = 0; j < x; j++) {
//            data[i][j]=new double*[y];
//            for (int k = 0; k < y; k++) {
//                data[i][j][k]=new double[z];
//            }
//        }
//    }
//
//
//
//    // Reopen the file, and this time we'll read the data
//    input.open(datFileName);
//    // Skip the first line
//    getline(input,line);
//
//    // Fill in the data
//    for (int i = 0; i < x; i++) {
//        for (int j = 0; j < y; j++) {
//             for (int k = 0; k < z; k++) {
//                getline(input,line);
//                /* cout << "This is the line:" <<line<<endl; */
//                iss.clear();
//                iss.str(line);
//                /* cout << "This is the line:" <<iss.str()<<endl; */
//                iss >> xhold >> yhold >> zhold;
//                iss >> std::scientific;
//                /* cout << "ijk:"<<i <<" "<<j << " " <<k << " "; */
//                /* cout << "ijk:"<<xhold <<" "<<yhold << " " <<zhold << " "; */
//                for (int m = 0; m < col; m++) {
//                    iss >> hold;
//                    data[m][i][j][k]=hold;
//                    /* cout << data[i][j][k][m] <<" "<<hold<<" "; */
//                }
//                /* cout << endl; */
//             }
//        }
//    }   
//
//    input.close();
//}
//
//void MuDataset:: outputVTKFile(){
//    ofstream output;
//
//
//    output.open(vtkFileName);
//    output << "# vtk DataFile Version 3.0\n";
//    output << "Structured Points\n";
//    output << "ASCII\n";
//    output << "\n";
//    output << "DATASET STRUCTURED_POINTS\n";
//    output << "DIMENSIONS " << std::to_string(x) << " " << std::to_string(y) <<" "<< std::to_string(z) << "\n";
//    output << "ORIGIN 0 0 0\n";
//    output << "SPACING " << 1 << " " << 1 << " " << 1 << "\n";
//    output << "\n";
//    output << "POINT_DATA " << std::to_string(x*y*z)+"\n";
//
//    for (int m = 0; m < col; m++) {
//
//        output << "SCALARS " << fileName << "_" << to_string(m) << " float\n";
//        output << "LOOKUP_TABLE default\n";
//        output << std::scientific;
//
//        for (int i = 0; i < x; i++) {
//            for (int j = 0; j < y; j++) {
//                for (int k = 0; k < z; k++) {
//                    output << data[m][i][j][k] << endl;; 
//                }
//            }
//        }   
//
//        output << endl;
//
//    }
//
//
//    output.close();
//
//    
//
//}
//
//void MuDataset::outputVTIFile(){
//
//    VTK_CREATE(vtkImageData,imageData);
//    imageData->SetDimensions(x,y,z);
//    VTK_CREATE(vtkDoubleArray,imageDataHold[col]);
//    /* imageDataHold[m]->AllocateScalars(VTK_DOUBLE,1); */
//    string tempName;
//    for (int m = 0; m < col; m++) {
//        imageDataHold[m]->SetNumberOfComponents(1);
//        imageDataHold[m]->SetNumberOfTuples(x*y*z);
//        tempName=fileName+"_"+to_string(m);
//        imageDataHold[m]->SetName(tempName.c_str());
//
//
//        for (int i = 0; i < x; i++) {
//            for (int j = 0; j < y; j++) {
//                for (int k = 0; k < z; k++) {
//                    imageDataHold[m]->SetValue(i+j*x+k*x*y,data[m][i][j][k]);
//                }
//            }
//        }   
//
//        imageData->GetPointData()->AddArray(imageDataHold[m]);
//
//    }
//    /* imageData->GetPointData()->SetScalars() */
//    /* int *dims=imageData->GetDimensions(); */
//
//    VTK_CREATE(vtkXMLImageDataWriter,writer);
//    writer->SetFileName(vtiFileName.c_str());
//    writer->SetInputData(imageData);
//    writer->Write();
//
//
//}
//
//
//



void VectorDomainDataset::readDatFile(){

    Dataset::readDatFile();

    /* cout << "After the base data read" << x << y << z<<endl; */

    domainIndex=new int**[x+2];
    for (int i = 0; i < x+2; i++) {
        domainIndex[i]=new int*[y+2];
        for (int j = 0; j < y+2; j++) {
            domainIndex[i][j]=new int[z+2]{2}; 
        }
    }

    domainCol = col/3;



}

void VectorDomainDataset::setOutputDomainAnalysisTrue(){
    outputDomainAnalysis = true;
}

void VectorDomainDataset::setOutputDomainAnalysisFalse(){
    outputDomainAnalysis = false;
}

void VectorDomainDataset::setOutputDomainAnalysis(bool input){
    outputDomainAnalysis = input;
}

double VectorDomainDataset::getDomainPercent(int index){
    return domainPercent[index];
}

int VectorDomainDataset::getDomainCount(int index){
    return domainCount[index];
}

int VectorDomainDataset::getDomainCountTotal(){
    return domainCountTotal;
}




void VectorDomainDataset::processDomain(VectorDomain domain,int choice){

    int current=0,ngrid_film=0,ngrid_sub=0;
    current=(choice-1)*3;

    domainPercent=new double [domain.getDomainTypeCount()]();
    domainCount=new int [domain.getDomainTypeCount()]();
    domainCountTotal=0;

    /* std::cout << "into the processing domain"<< endl; */
    for (int i = 0; i < z; i++) {
        for(int j = 0; j < y; j++){
            for (int k = 0; k < x; k++) {
                if(std::abs(data[current][k][j][i])+std::abs(data[current+1][k][j][i])+std::abs(data[current+2][k][j][i])>0.000001){
                    ngrid_film = i;
                    break;
                }
            }
        }
    }

    for (int i = z-1; i >=0; i--) {
        for(int j = 0; j < y; j++){
            for (int k = 0; k < x; k++) {
                if(std::abs(data[current][k][j][i])+std::abs(data[current+1][k][j][i])+std::abs(data[current+2][k][j][i])>0.000001){
                    ngrid_sub = i;
                    break;
                }
            }
        }
    }

    /* std::cout << "into the processing domain"<< endl; */
    for (int i = 0; i < x+2; i++) {
        for (int j = 0; j < y+2; j++) {
            for (int k = 0; k < z+2; k++) {
                if (i*j*k==0 || (i-x-1)*(j-y-1)*(k-z-1)==0) {
                    domainIndex[i][j][k]=-1;
                }else if(k>=ngrid_film+2){
                    domainIndex[i][j][k]=-1;
                }else if(k<=ngrid_sub){
                    domainIndex[i][j][k] = 0;
                }
            }
        }
    }


    /* std::cout << "into the processing domain"<< ngrid_film << " " <<ngrid_sub<<endl; */


    for (int i = 1; i < x+1; i++) {
        for(int j = 1; j < y+1; j++){
            for (int k = ngrid_sub+1; k < ngrid_film+2; k++) {
                domainIndex[i][j][k]=domain.getDomainType(data[current][i-1][j-1][k-1],data[current+1][i-1][j-1][k-1],data[current+2][i-1][j-1][k-1]);
                if (domainIndex[i][j][k]!=-1) {
                    domainCount[domainIndex[i][j][k]]++;
                }
                /* cout <<"The domain type of "<< i << " "<<j<<" "<<k<<" is "<< domainIndex[i][j][k]<<endl; */
            }
        }
    }

    for (int i = 0; i < x+2; i++) {
        for (int j = 0; j < y+2; j++) {
            for (int k = 0; k < z+2; k++) {
                /* cout <<"The domain type of "<< i << " "<<j<<" "<<k<<" is "<< domainIndex[i][j][k]<<endl; */
           }
        }
    }



    for (int i = 0; i < domain.getDomainTypeCount(); i++) {
        domainCountTotal=domainCountTotal+domainCount[i];
    }
    for (int j = 0; j < domain.getDomainTypeCount(); j++) {
        domainPercent[j]=domainCount[j]/double(domainCountTotal);
        /* cout << "domain percentage of " << j << " is " << domainPercent[j] << " " <<domainHold[j]<< endl; */ 
    }







}

void VectorDomainDataset::outputVTIFile(VectorDomain domain,int choice){
    VTK_CREATE(vtkImageData,imageData);
    imageData->SetDimensions(x+2,y+2,z+2);
    // VTK_CREATE(vtkDoubleArray,imageDataHold[domainCol]);

    vtkSmartPointer<vtkDoubleArray> imageDataHold[domainCol];
    for (int i = 0; i < domainCol; ++i)
    {
        imageDataHold[i]= vtkSmartPointer<vtkDoubleArray>::New();
    }

    VTK_CREATE(vtkIntArray,imageDomainType);
    string tempName;
    int domainNum;


    processDomain(domain,choice);

    imageDomainType->SetNumberOfComponents(1);
    imageDomainType->SetNumberOfTuples((x+2)*(y+2)*(z+2));
    tempName="domain";
    imageDomainType->SetName(tempName.c_str());
            for (int k = 0; k < z+2; k++) {
        for(int j = 0; j < y+2; j++){
    for (int i = 0; i < x+2; i++) {
                /* domainNum=domain.getDomainType(data[current][i][j][k],data[current+1][i][j][k],data[current+2][i][j][k]); */
                imageDomainType->SetTuple1(i+j*(x+2)+k*(x+2)*(y+2),domainIndex[i][j][k]);
                /* imageDomainType->SetTuple1(i+j*x+k*x*y,k); */
                /* cout << "outputing vti file " <<i<<j<<k<< " "<< domainLabel[i][j][k] << " " << domainHold[17] << " " <<domainHold[21] << endl; */ 
                /* cout << "outputing vti file " <<i<<" "<<j<< " "<<k<< " "<< imageDomainType->GetTuple1(i+j*x+k*x*y) << endl; */ 
            }
        }
    }
    imageData->GetPointData()->AddArray(imageDomainType);
    /* cout << "The domain type amount is "<<domain.getDomainTypeCount()<<endl; */

    if (outputDomainAnalysis) {
        Data domainInfo;
        domainInfo.setFileName(longFileName+".txt");
        vector<string> header(5);
        vector<double> value(2);
        header[0] = "Domain index";
        header[1] = "Domain label";
        header[2] = "Percentage";
        header[3] = "Count";
        header[4] = to_string(domainCountTotal);
        domainInfo.initializeFile(header);
        for (int i = 0; i <domain.getDomainTypeCount(); i++) {
            value[0] = domainPercent[i];
            value[1] = domainCount[i];
            domainInfo.outputWithIndexAndName(i,domain.getDomainTypeLabel(i),value); 
        }


    }

    /* cout << "The domain type amount is "<<domainCol<<endl; */

    for(int m=0;m<domainCol;m++){
        imageDataHold[m]->SetNumberOfComponents(3);
        imageDataHold[m]->SetNumberOfTuples((x+2)*(y+2)*(z+2));
        tempName="vector_"+to_string(m);
        imageDataHold[m]->SetName(tempName.c_str());

        for (int i = 0; i < x+2; i++) {
            for(int j = 0; j < y+2; j++){
                for (int k = 0; k < z+2; k++) {
                    if (i*j*k == 0 || (i-x-1)*(j-y-1)*(k-z-1)==0) {
                        imageDataHold[m]->SetTuple3(i+j*(x+2)+k*(x+2)*(y+2),0,0,0);
                    }else{
                        imageDataHold[m]->SetTuple3(i+j*(x+2)+k*(x+2)*(y+2),data[m*3][i-1][j-1][k-1],data[m*3+1][i-1][j-1][k-1],data[m*3+2][i-1][j-1][k-1]);
                    }

                }
            }
        }
        imageData->GetPointData()->AddArray(imageDataHold[m]);
    }

    VTK_CREATE(vtkXMLImageDataWriter,writer);
    writer->SetFileName(vtiFileName.c_str());
    writer->SetDataModeToBinary();
    writer->SetInputData(imageData);
    writer->Write();
}

