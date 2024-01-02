#include <Data.h>
#include <fstream>
#include <iostream>
#include <iomanip>

using namespace std;
Data::Data(){}
Data::~Data(){}

void Data::initializeFile(std::vector<std::string> header){
    ofstream file;
    int length;
    if (fileName.empty()) {
        fileName="default.dat";
    }

    file.open(fileName,ios::trunc);
    length=header.size();
    for (int i = 0; i < length; i++) {
        file << setw(15) << header[i] ;
    }
    file << std::endl; 
    file.close();
}

void Data::setFileName(std::string name){
    fileName=name;
}

std::string Data::getFileName(){
    return fileName;
}

void Data::outputWithoutIndex(std::vector<double> value){
    ofstream file;
    int length;
    file.open(fileName,ios::app);
    length=value.size();
    for (int i = 0; i < length; i++) {
        file << std::scientific <<setw(15) << value[i] ; 
    }
    file <<  std::endl;
    file.close();

}

void Data::outputWithIndex(int index,std::vector<double> value){
    ofstream file;
    int length;
    file.open(fileName,ios::app);
    length=value.size();
    file << setw(15) << index ;
    for (int i = 0; i < length; i++) {
        file << std::scientific <<setw(15) << value[i] ; 
    }
    file <<  std::endl;
    file.close();

}

void Data::outputWithName(std::string name,std::vector<double> value){
    ofstream file;
    int length;
    file.open(fileName,ios::app);
    length=value.size();
    file << setw(15) << name ;
    for (int i = 0; i < length; i++) {
        file << std::scientific <<setw(15) << value[i] ; 
    }
    file <<  std::endl;
    file.close();
}

void Data::outputWithIndexAndName(int index,std::string name,std::vector<double> value){
    ofstream file;
    int length;
    file.open(fileName,ios::app);
    length=value.size();
    file << setw(15) << index << std::right << setw(15) << name ;
    for (int i = 0; i < length; i++) {
        file << std::scientific <<setw(15) << value[i] ; 
    }
    file <<  std::endl;
    file.close();
}

void Data::outputWithPosition(std::vector<int> position,std::vector<double> value){
    ofstream file;
    int length;
    file.open(fileName,ios::app);
    length=position.size();
    for (int i = 0; i < length; i++) { 
        file << setw(15) <<  position[i];
    }
    length=value.size();
    for (int i = 0; i < length; i++) {
        file << std::scientific <<setw(15) << value[i] ; 
    }
    file <<  std::endl;
    file.close();


}
