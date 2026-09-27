#include <FreeFormatParser.h>
#include <fstream>
#include <iostream>
#include <vector>
#include <algorithm>

using namespace std;
FreeFormatParser::FreeFormatParser(){
    filename = "";
    firstLevelLength = 0;
    secondLevelLength = 0;
}

FreeFormatParser::FreeFormatParser(string name){
    filename=name;
    firstLevelLength = 0;
    secondLevelLength = 0;
}

FreeFormatParser::~FreeFormatParser(){
}

void FreeFormatParser::setFilename(string name){
    filename=name;
}

vector<string> FreeFormatParser::getFirstLevel(string firstLevelName){
    vector<string> value;
    transform(firstLevelName.begin(),firstLevelName.end(),firstLevelName.begin(),::toupper);
    for (int i = 0; i < firstLevelLength; i++) {
        /* cout << "compare fisrt " << firstLevel[i][0] << firstLevelName <<endl; */
        if(firstLevel[i][0]==firstLevelName){
            /* cout << "Inside the correct part" << endl; */
            value.push_back(firstLevel[i][1]);
            /* break; */
        }
    }
    return value;
}

vector<string> FreeFormatParser::getFirstLevel(int i){
    vector<string> value;
    if ( i <= firstLevelLength) {
        /* cout << "compare fisrt " << firstLevel[i][0] << firstLevelName <<endl; */
        value.push_back(firstLevel[i][0]);
        value.push_back(firstLevel[i][1]);
            /* break; */
    }
    return value;
}

bool FreeFormatParser::firstKeyExist(string firstLevelName){
    bool value=false;
    for (int i = 0; i < firstLevelLength; i++) {
        /* cout << "compare fisrt " << firstLevel[i][0] << firstLevelName <<endl; */
        if(firstLevel[i][0]==firstLevelName){
            value=true;
            break;
        }
    }

    return value;
}

vector<string> FreeFormatParser::getSecondLevel(string firstLevelName,string secondLevelName){
    vector<string> value;
    transform(secondLevelName.begin(),secondLevelName.end(),secondLevelName.begin(),::toupper);
    for (int i = 0; i < secondLevelLength; i++) {
        /* cout << "compare second" << secondLevel[i][0] << secondLevel[i][1] << firstLevelName << secondLevelName <<endl; */
        if(secondLevel[i][0]==firstLevelName && secondLevel[i][1]==secondLevelName){
            /* cout << "Inside the correct part" << secondLevel[i][2] << endl; */
            value.push_back(secondLevel[i][2]);
            /* break; */
        }
    }
    return value;

}

vector<string> FreeFormatParser::getSecondLevel(int i){
    vector<string> value;
    if ( i < secondLevelLength) {
        /* cout << "compare second" << secondLevel[i][0] << secondLevel[i][1] << firstLevelName << secondLevelName <<endl; */
            /* cout << "Inside the correct part" << secondLevel[i][2] << endl; */
            value.push_back(secondLevel[i][0]);
            value.push_back(secondLevel[i][1]);
            value.push_back(secondLevel[i][2]);
            /* break; */
    }
    return value;
}


vector<vector<string> > FreeFormatParser::getFirstWhole(){
    return firstLevel;
}

void FreeFormatParser::setFirstWhole(vector<vector<string>> firstIn){
    firstLevel = firstIn;
}

void FreeFormatParser::setSecondWhole(vector<vector<string>> secondIn){
    secondLevel = secondIn;
}


vector<vector<string> > FreeFormatParser::getSecondWhole(){
    return secondLevel;
}


int FreeFormatParser::getFirstLevelLength(){
    return firstLevelLength;
}

int FreeFormatParser::getSecondLevelLength(){
    return secondLevelLength;
}

bool FreeFormatParser::secondKeyExist(string firstLevelName,string secondLevelName){
    bool value=false,first=false,second=false;

    for (int i = 0; i < firstLevelLength; i++) {
        /* cout << "compare first" << i << " "<<firstLevel[i][0] << firstLevel[i][1] << firstLevelName << secondLevelName <<endl; */
        if(firstLevel[i][1]==firstLevelName){
            first=true;
            break;
        }
    }


    for (int i = 0; i < secondLevelLength; i++) {
        /* cout << "compare second" << i << " "<<secondLevel[i][0] << secondLevel[i][1] << secondLevel[i][2] << firstLevelName << secondLevelName <<endl; */
        if(secondLevel[i][0]==firstLevelName && secondLevel[i][1]==secondLevelName){       
            second=true;
            break;
        }
    }
    value = first && second;
    return value;

}

//template <typename T>
//void FreeFormatParser::getValue(string name,T output,string trueMessage,string falseMessage){
//    if (firstKeyExist(name)){
//        istringstream(getFirstLevel(name)[0]) >> output;
//    print.printVariable(trueMessage,output);
//    }else{
//    print.printVariable(falseMessage,output);}
//}

bool FreeFormatParser::parse(){
    string line;
    string firstId,secondId,value,comment;
    ifstream freeFile(filename,std::ifstream::in);
    /* cout << "inside the parser"<< filename <<endl; */
    if(ifstream(filename)){
        firstLevelLength=0;
        secondLevelLength=0;
        /* cout << "inside the if else"<<endl; */
        while(getline(freeFile,line)){
            FreeFormatOneLine lineHold(line);
            lineHold.split();
            firstId=lineHold.getFirstLevelIdentifier();
            secondId=lineHold.getSecondLevelIdentifier();
            value=lineHold.getValues();
            comment=lineHold.getComment();

            /* cout << "inside the while loop"<<firstId<<" "<<secondId<<" "<<endl; */
            if(secondId=="" && firstId!=""){

                transform(firstId.begin(),firstId.end(),firstId.begin(),::toupper);
                vector<string> first;
                first.resize(3);
                first[0]=firstId;
                first[1]=value;
                first[2]=comment;
                firstLevel.push_back(first);
                firstLevelLength++;
            /* std::cout << "FirstLevel" << first[0] << first[1] << first[2] <<std::endl; */
            }else if(firstId!="" && secondId!=""){
                transform(secondId.begin(),secondId.end(),secondId.begin(),::toupper);
                vector<string> second;
                second.resize(4);
                second[0]=firstId;
                second[1]=secondId;
                second[2]=value;
                second[3]=comment;
                secondLevel.push_back(second);
                secondLevelLength++;
            /* std::cout << "SecondLevel" << second[0] << second[1] << second[2] <<std::endl; */
            }
        }
        freeFile.close();
        return true;
    }else{
        /* std::cout << filename << " does not exist" << std::endl; */
        return false;
    }
}

void FreeFormatParser::write(std::string filename){
    ofstream output;
    output.open(filename);
    for (auto &it : firstLevel){ 
        output << it[0] << " = " << it[1] ;
        if (it[2] != "") {
            output << " # " << it[2] ;
        }
        output << std::endl;
    }
    for (auto &it : secondLevel){
        output << it[0] << "." << it[1] << " = " << it[2] ;
        if (it[3] != "") {
            output << " # " << it[3];
        }
        output << std::endl;
    } 
    output.close();

}

template <typename T>
vector<T> FreeFormatParser::readKeyword(string keyword){
  std::string nameHold;
  vector<string> vecHold;
  vector<T> outVector;
  if (this->firstKeyExist(keyword)) {
    vecHold = this->getFirstLevel(keyword);
    //for (auto &it : vecHold) {
      //istringstream iss(it);
      //while(iss){
        //iss >> nameHold;
        //outVector.push_back(nameHold);
      //}
    //}
    outVector = vecHold;
  }
  return outVector;
}
