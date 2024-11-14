struct fileGroup{
    std::string group;
    std::string name;
};
bool fileExist(const char *filename){
    ifstream file(filename);
    return (bool)file;
}

std::vector<fileGroup> findObjects(FreeFormatParser structRead,std::string fileKey,std::vector<std::string> groupKey){
    fileGroup fileGroup_hold;
    std::vector<fileGroup> output;
    std::vector<std::string> vecHold;
    std::string nameHold;
    if (structRead.firstKeyExist(fileKey)) {
        vecHold = structRead.getFirstLevel(fileKey);
        for ( auto &it : vecHold) {
            istringstream iss(it);
            while(iss){
                iss >> nameHold;
                fileGroup_hold.name = nameHold;
                fileGroup_hold.group = "";
                output.push_back(fileGroup_hold);
            }
        }
    }

    for ( auto &git : groupKey){
        if (structRead.secondKeyExist(git,fileKey)) {
            vecHold = structRead.getSecondLevel(git,fileKey);
            for (auto &it : vecHold) {
                istringstream iss(it);
                while(iss){
                    iss >> nameHold;
                    fileGroup_hold.name = nameHold;
                    fileGroup_hold.group = git;
                    output.push_back(fileGroup_hold);
                }
            }
        }
    }
    return output;
} 

std::vector<std::string> findObjects(FreeFormatParser structRead,std::string fileKey){
    fileGroup fileGroup_hold;
    std::vector<std::string> output;
    std::vector<std::string> vecHold;
    std::string nameHold;
    if (structRead.firstKeyExist(fileKey)) {
        vecHold = structRead.getFirstLevel(fileKey);
        for ( auto &it : vecHold) {
            istringstream iss(it);
            while(iss){
                iss >> nameHold;
                output.push_back(nameHold);
            }
        }
    }

    return output;
} 

std::string removeSlash(std::string groupName){
    std::string outName;
    if (groupName[0]=='/') {
        outName = groupName.substr(1);
    }else{
        outName = groupName;
    }
    /* cout << "group name" << groupName << outName << endl; */
    return outName;
}

