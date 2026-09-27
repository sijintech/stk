#include <DataHDF5IO.h>
#include <TxtHDF5IO.h>
#include <FreeFormatOneLine.h>
#include <FreeFormatParser.h>
#include <TableHDF5IO.h>
#include <H5File.h>
#include <ScreenPrint.h>
#include <string.h>
#include <unistd.h>
#include <FileExist.hpp>
/* using namespace H5; */

int main(int argc, char *argv[]){
    DataHDF5IO polarData;
    TableHDF5IO inputData,energyout,potData,fixData;
    TxtHDF5IO txtData;
    H5File comment;
    FreeFormatParser structRead;
    ScreenPrint print;
    print.setWidth(120);
    print.setColumnWidth(60);
    print.setNumberWidth(11);
    std::string h5Name,nameHold,strHold,backupStyle;
    bool controlFileExist=false;
    vector<fileGroup> datFile,freeFile,fixFile,jsonFile,tdFile,txtFile,message;
    fileGroup fileGroup_hold;
    vector<string> vecHold,groupName,folderList;
    int i,start;

    structRead.setFilename("backupRestore.in");
    controlFileExist = structRead.parse();

    h5Name = "backup.h5";
    if (controlFileExist) {
        print.printCenter("Start to read backupRestore.in file",'-');
        vecHold.clear();

        h5Name = structRead.readKeyword("FILE")[0];
        backupStyle = structRead.readKeyword("STYLE")[0];
        groupName = findObjects(structRead,"GROUP");
        freeFile = findObjects(structRead,"FREE",groupName);
        message = findObjects(structRead,"COMMENT",groupName);
        fixFile = findObjects(structRead,"FIX",groupName);
        tdFile = findObjects(structRead,"TIME",groupName);
        jsonFile = findObjects(structRead,"JSON",groupName);
        txtFile = findObjects(structRead,"TXT",groupName);

        freeFile = structRead.readKeyword("FREEINPUT");
        fixFile = structRead.readKeyword("FIXINPUT");
        tdFile = structRead.readKeyword("TIMEDEPEND");
        message = structRead.readKeyword("COMMENT");
        jsonFile = structRead.readKeyword("JSON");
        txtFile = structRead.readKeyword("TXT"); 

    }else {

        if(argc > 1){
            fileGroup_hold.name = "energy_out.dat";
            fileGroup_hold.group = "Output";
            tdFile.push_back(fileGroup_hold);
            print.printCenter("Using the default energy_out.dat",' ');
            print.printCenter("Get dat file name from command line",'-');
            strHold = argv[1];
            if (strHold.substr(strHold.find_last_of(".")+1) == "h5") {
                nameHold = "Output to the " + strHold;
                print.printCenter(nameHold,' ');
                h5Name = strHold;
                start = 2;
            }else{
                print.printCenter( "Output to the default backup.h5.",' ');
                h5Name = "backup.h5";
                start = 1;
            }
            for ( i = start; i < argc; i++) {
                strHold = argv[i];
                if (strHold == "-m") {
                    i++ ; 
                    /* nameHold = argv[i]; */
                    fileGroup_hold.name = argv[i];
                    fileGroup_hold.group = "/";
                    message.push_back(fileGroup_hold);
                }else{
                    nameHold = "Using the data file " + strHold;
                    fileGroup_hold.name = strHold;
                    fileGroup_hold.group = "Output";
                    datFile.push_back(fileGroup_hold); 
                    print.printCenter(nameHold,' ');
                }
            }

        }else{
            print.printLeft("Warning, no backupRestore.in file, and no command line argument ",' ');
            print.printCenter("Output to the default backup.h5, only input is backuped.",' ');
            h5Name = "backup.h5";
        }
        if (fileExist("input.in")) {
            fileGroup_hold.name = "input.in";
            fileGroup_hold.group = "Input";
            freeFile.push_back(fileGroup_hold);
            print.printCenter("Using the default input.in",' '); 
        }else if(fileExist("inputN.in")){
            fileGroup_hold.name = "inputN.in";
            fileGroup_hold.group = "Input";
            fixFile.push_back(fileGroup_hold);
            print.printCenter("Using the default inputN.in",' '); 
        }else if(fileExist("parameter.in")){
            fileGroup_hold.name = "parameter.in";
            fileGroup_hold.group = "Input";
            fixFile.push_back(fileGroup_hold);
            print.printCenter("Using the default parameter.in",' '); 
        }

        if (fileExist("structgen.in")) {
            fileGroup_hold.name = "structgen.in";
            fileGroup_hold.group = "Input";
            freeFile.push_back(fileGroup_hold);
            print.printCenter("Using the default structgen.in",' ');
        }

        if (fileExist("Polar.in")) {
            fileGroup_hold.name = "Polar.in";
            fileGroup_hold.group = "Input";
            datFile.push_back(fileGroup_hold);
            print.printCenter("Using the default Polar.in",' ');
        }


        if (fileExist("pot.in")) {
            fileGroup_hold.name = "pot.in";
            fileGroup_hold.group = "Input";
            jsonFile.push_back(fileGroup_hold);
            print.printCenter("Using the default pot.in",' ');
            int i = 1;
            nameHold="pot"+to_string(i)+".in";
            while(fileExist(nameHold.c_str())){
                i = i+1;
                strHold="pot"+to_string(i)+".in";
                fileGroup_hold.name = strHold;
                fileGroup_hold.group = "Input";
                jsonFile.push_back(fileGroup_hold);
                nameHold = "Using the default " + strHold;
                print.printCenter( nameHold,' ');
            }
        }

        if (fileExist("batch.sh")) {
            fileGroup_hold.name = "batch.sh";
            fileGroup_hold.group = "Input";
            txtFile.push_back(fileGroup_hold);
            print.printCenter("Using the default batch.sh",' ');
        }
        if (fileExist("Ferroelectric.pbs")) {
            fileGroup_hold.name = "Ferroelectric.pbs";
            fileGroup_hold.group = "Input";
            txtFile.push_back(fileGroup_hold);
            print.printCenter("Using the default Ferroelectric.pbs",' ')        if (structRead.firstKeyExist("FILE")) {
            vecHold = structRead.getFirstLevel("FILE");
            h5Name = vecHold[0];
        };
        }
        if (fileExist("backupRestore.in")) {
            fileGroup_hold.name = "backupRestore.in";
            fileGroup_hold.group = "Input";
            txtFile.push_back(fileGroup_hold);
            print.printCenter("Using the default backupRestore.in",' ');
        }

    }

    if (message.size() > 0) {
        comment.setH5FileName(h5Name);
        comment.addRootComment("Comment",message[0].name);
    }


    if (backupStyle[0] == "B" || backupStyle[0] == "b"){
      folderList = parseBatchList("batchList.txt");
    }else{
      folderList.push_back("");
    }


    for (auto &folder : folderList){

      for (auto &it : datFile) {
        polarData.setDatFileName(it.name);
        polarData.setH5FileName(h5Name);
        polarData.readDatwriteH5(folder+"/"+it.group);
        /* polarData.outputH5("output"); */
        polarData.cleanDat();
      }
      std::cout << "going to the time dependent" << std::endl;
      for (auto &it : tdFile) {
        energyout.setDatFileName(it.name);
        energyout.setH5FileName(h5Name);
        energyout.readTimeDependentFile();
        energyout.outputH5(folder+"/"+it.group);
        energyout.cleanDat();
      }

      std::cout << "going to the input data" << std::endl;
      for (auto &it : freeFile) {
        inputData.setDatFileName(it.name);
        inputData.setH5FileName(h5Name);
        inputData.readFreeFormatFile();
        inputData.outputH5(folder+"/"+it.group);
        inputData.cleanDat();
      }

      std::cout << "going to the potential data" << std::endl;
      for (auto &it : jsonFile) {
        potData.setDatFileName(it.name);
        potData.setH5FileName(h5Name);
        potData.readJSONFile();
        potData.outputH5(folder+"/"+it.group);
        potData.cleanDat();
      }
      std::cout << "going to the fix data" << std::endl;
      for (auto &it : fixFile) {
        fixData.setDatFileName(it.name);
        fixData.setH5FileName(h5Name);
        fixData.readFixFormatFile();
        fixData.outputH5(folder+"/"+it.group);
      }
      std::cout << "going to the txt data" << std::endl;
      for (auto &it : txtFile) {
        txtData.setDatFileName(it.name);
        txtData.setH5FileName(h5Name);
        txtData.readTXTFile();
        txtData.outputH5(folder+"/"+it.group);
      }

    }





    return 0;
}

unsigned getNumberOfDigits (unsigned i)
{
    return i > 0 ? (int) log10 ((double) i) + 1 : 1;
}

unsigned getFileLineNumber(string fileName){
  ifstream file(fileName);
  string line;
  size_t lines_count=0;
  while(getline(file,line))
    ++lines_count;
  return lines_count;
}

vector<string> parseBatchList(string batchFile){
  ifstream file(batchFile);
  stringstream oneFile;
  SplittableString batchLine;
  batchLine.setDeliminator("|");
  vector<string> outVector,lineVector,keywordList,valueList;
  string sep;
  unsigned batchIndexDigit=0;

  size_t lineVectorSize,batchLineNumber;
  batchIndexDigit = getNumberOfDigits(getFileLineNumber(batchFile));
  if (file.is_open()) {
    getline(file,line);
    batchLine.setText(line);
    lineVector = batchLine.split(); 
    lineVectorSize = batchLine.getSize();
    sep = lineVector[0];

    for (int i=1;i<lineVectorSize-1;i++){
      keywordList.push_back(lineVector[i])
    }

    while(getline(file,line)){
      batchLine.setText(line);
      lineVector = batchLine.split();  
      index = lineVector[0];

      oneFile << setw(batchIndexDigit) << setfill('0') << index << sep;
      for (int i=1;i<lineVectorSize-1;i++){
        valueList.push_back(lineVector[i])
        oneFile << sep << keywordList[i-1] << "_" << lineVector[i] ;
      }
      outVector.push_back(oneFile);

    }
  }
  
}
