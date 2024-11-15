#include <FileNamer.h>
#include <vector>
#include <SplittableString.h>
#include <sstream>
#include <fstream>
#include <iomanip>
#include <iostream>

using namespace std;

FileNamer::FileNamer(){
    inName = "";
    outName="";
    extension="";
    shortName="";
    longName="";
}
FileNamer::FileNamer(string nameIn){
    inName = nameIn;
    outName = "";
   SplittableString name(inName,".");
   extension = name.getLast();
   shortName = name.getFirst();
   longName = name.getFirst()+"."+name.getMiddle();

}

FileNamer::~FileNamer(){}

void FileNamer::setInName(string nameIn){
    inName = nameIn;
   SplittableString name(inName,".");
   extension = name.getLast();
   shortName = name.getFirst();
   longName = name.getFirst()+"."+name.getMiddle();
}

string FileNamer::getInName(){
    return inName;
}

string FileNamer::autoNamer(){
   string indexString;
   int index;
   stringstream ss;

   index = 0;
   ss.clear();
   ss.str("");
   ss << setw(3) << setfill('0') << index;
   indexString = ss.str();

   outName = longName+"."+indexString+"."+extension;   

   while(ifstream(outName)){
    index=index+1;
    ss.clear();
    ss.str("");
    ss << setw(3) << setfill('0') << index;
    indexString = ss.str();
    outName = longName+"."+indexString+"."+extension;   
   }
   return outName;
}

void FileNamer::setExtension(string ext){
    extension = ext;
}
