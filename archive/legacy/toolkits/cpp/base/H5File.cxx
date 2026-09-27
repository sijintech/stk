#include <H5File.h>
#define MAX_NAME 1024

using namespace std;

H5File::H5File(){
    file_id = -1;
    group_id = -1;
    dataset_id = -1;
    h5FileName = "backup.h5";
    datFileName = "";
    fileType = "";
}

H5File::~H5File(){
}

void H5File::clear(){
    file_id = -1;
    group_id = -1;
    dataset_id = -1;
    h5FileName = "backup.h5";
    datFileName = "";
    fileType = "";

}

void H5File::setH5FileName(string filename){
    h5FileName = filename;
}

void H5File::setDatFileName(string datFile){
    datFileName = datFile;
}

hid_t H5File::openH5File(bool create){
    ifstream ifile(h5FileName.c_str());
    if (ifile) {
        file_id = H5Fopen(h5FileName.c_str(),H5F_ACC_RDWR,H5P_DEFAULT);
        file_open = true;
        return file_id;
    }else{
        if (create) {
            file_open = true;
            file_id = H5Fcreate(h5FileName.c_str(),H5F_ACC_TRUNC,H5P_DEFAULT,H5P_DEFAULT);
        }else{
            file_open = false;
            cout << "Error the " << h5FileName << " does not exist." << endl;
        }
    }
    return file_id;
}

hid_t H5File::openH5Group(string groupName,bool create){
    string wholeGroupName;
    herr_t status;
    if (groupName[0] == '/') {
        wholeGroupName = groupName;
    }else{
        wholeGroupName = '/' + groupName;
    }
    
    if ((int)file_id < 0) {
        openH5File(false);
        if ((int)file_id < 0) {
            cout << h5FileName << " does not open correctly." << endl;
        }else{
            openH5Group(groupName,create);
        }
    }else{
        /* if (groupName != "") { */
        status = H5Gget_objinfo(file_id,wholeGroupName.c_str(),0,NULL);
        /* } */
        if (status == 0 ) {
            group_id = H5Gopen(file_id,wholeGroupName.c_str(),0);
            group_open = true;
        }else{
            if (create) {
                group_id = H5Gcreate(file_id,wholeGroupName.c_str(),H5P_DEFAULT,H5P_DEFAULT,H5P_DEFAULT);
                group_open = true;
            }else{
                group_open = false;
                cout << "Error, the group name " << wholeGroupName << " does not exist." << endl;
            }
        }
    }
    return group_id;
}

void H5File::H5FGclose(){
    if (file_open) {
        H5Fclose(file_id);
    }

    if (group_open) {
        H5Gclose(group_id);
    }
}
//herr_t H5File::op_func(hid_t loc_id,const char *name,const H5L_info_t *info, void *operator_data){
//    herr_t status;
//    dataset hold;
//    H5O_info_t infobuf;
//
//    status = H5Oget_info_by_name(loc_id,name,&infobuf,H5P_DEFAULT);
//    switch (infobuf.type){
//        case H5O_TYPE_GROUP:
//            groupList.push_back(name);
//            status = H5Literate_by_name(loc_id,name,H5_INDEX_NAME,H5_ITER_NATIVE,NULL,op_func,)
//            break;
//        case H5O_TYPE_DATASET:
//            hold.
//            break;
//        default:
//            cout << "The data " << name << " is not a group nor dataset." << endl;
//    } 
//    return status;
//}

void H5File::parseH5File(){
    dataList.clear();
    groupList.clear();
    attributeList.clear();
    openH5File(false);
    openH5Group("/",false);
    groupList.push_back("/");
    /* cout << "groupList" << groupList[0] << endl; */
    scanGroup(group_id,"/");
    /* cout << "groupList2" << groupList[0] << endl; */
}

vector<attr> H5File::scanAttribute(hid_t oid, string name){
    int na;
    ssize_t len;
    hid_t atype,aid;
    herr_t status;
    hid_t aspace;
    attr hold;
    vector<attr> outputAttr;
    string strHold;
    char bufName[MAX_NAME],bufValue[MAX_NAME];
    na = H5Aget_num_attrs(oid);
    outputAttr.clear();
    for (int i = 0; i < na; i++) {
        aid = H5Aopen_idx(oid,(unsigned int)i);
        len = H5Aget_name(aid,MAX_NAME,bufName);
        atype = H5Aget_type(aid);
        aspace = H5Aget_space(aid);
        status = H5Aread(aid,atype,bufValue);
        strHold = bufName;
        hold.attributeName = strHold;
        strHold = bufValue;
        hold.attributeValue = strHold;
        hold.dataName = name;
        attributeList.push_back(hold);
        outputAttr.push_back(hold);
        H5Tclose(atype);
        H5Sclose(aspace);
        H5Aclose(aid);
    }
    return outputAttr;
}


string H5File::trim(string str){
    size_t first = str.find_first_not_of(' ');
    if (string::npos == first) {
        return str;
    }
    size_t last = str.find_last_not_of(' ');
    return str.substr(first,(last-first+1));
}

void H5File::addRootComment(string attrName,string attrValue){
    openH5File(true);
    openH5Group("/",true);
    writeStrAttribute(group_id,attrName,attrValue);
}

string H5File::readRootComment(string attrName){
    string out;
    openH5File(false);
    openH5Group("/",false);
    out = "";
    out = readStrAttribute(group_id,attrName);
    return out;
}

void H5File::writeStrAttribute(hid_t id,string attrName,string attrValue){
    hid_t atype,aspace,aid;
    char attributeHold[MAX_NAME];
    herr_t status;
    atype = H5Tcopy(H5T_C_S1);
    H5Tset_size(atype,MAX_NAME);
    aspace = H5Screate(H5S_SCALAR);
    strcpy(attributeHold,attrValue.c_str());
    aid = H5Acreate(id,attrName.c_str(),atype,aspace,H5P_DEFAULT,H5P_DEFAULT);
    status = H5Awrite(aid,atype,attributeHold);
    H5Aclose(aid); 
    H5Sclose(aspace);
    H5Tclose(atype);
}

string H5File::readStrAttribute(hid_t id,string attrName){
    hid_t aid,atype;
    char bufValue[MAX_NAME];
    herr_t status;
    string outputString;
    aid = H5Aopen(id,attrName.c_str(),H5P_DEFAULT);
    atype = H5Aget_type(aid);
    status = H5Aread(aid,atype,bufValue);
    if (status >= 0) {
        outputString = trim(bufValue);
    }else{
        outputString = "";
    }
    H5Tclose(atype);
    H5Aclose(aid);
    return outputString;
}

void H5File::scanGroup(hid_t gid,std::string groupBase){
    ssize_t len;
    hid_t did,grpid;
    string newGroupBase;
    hsize_t nobj;
    dataset hold;
    herr_t status;
    char memb_name[MAX_NAME],group_name[MAX_NAME];
    int otype;
    len = H5Iget_name(gid,group_name,MAX_NAME);
    scanAttribute(gid,groupBase);
    status = H5Gget_num_objs(gid,&nobj);
    for (int i = 0; i < nobj; i++) {
        /* cout << "inside scan group"<<i << endl; */
        len = H5Gget_objname_by_idx(gid,(hsize_t) i,memb_name,(size_t)MAX_NAME);
        otype = H5Gget_objtype_by_idx(gid,(size_t)i);
        /* cout << "inside scan group"<<i << endl; */
        switch(otype){
            case H5G_LINK:
                cout << "A link " << memb_name <<" in group " << group_name << endl;
                break;
            case H5G_GROUP:
                cout << "A group " << memb_name <<" in group " << group_name << endl;
//                if (groupBase == "" || groupBase == "/"){
//                    newGroupBase = "/"
//                }else if (groupBase[0] != '/') {
//                    newGroupBase = "/" + groupBase + "/";
//                }else{
//                    newGroupBase = groupBase + "/";
//                }
                newGroupBase = getTrueGroupName(groupBase);
                newGroupBase = newGroupBase + "/" + memb_name;
                groupList.push_back(newGroupBase);
                grpid = H5Gopen(gid,memb_name,0);
                scanGroup(grpid,newGroupBase);
                H5Gclose(grpid);
                break;
            case H5G_DATASET:
                cout << "A dataset " << memb_name << " in group " << group_name << endl; 
                hold.groupName = groupBase;
                hold.dataName = memb_name;
                hold.wholeName = hold.groupName + "/" + hold.dataName;
                /* cout << "A dataset " << memb_name << " in group " << group_name << endl; */ 
                did = H5Dopen(gid,hold.dataName.c_str(),H5P_DEFAULT);
                /* cout << "A dataset " << memb_name << " in group " << group_name << endl; */ 
                /* scanAttribute(did,hold.wholeName); */
                hold.fileType = readStrAttribute(did,"File Type");
                /* cout << "A dataset " << memb_name << " in group " << group_name << endl; */ 
                /* cout << hold.groupName << endl; */
                /* cout << "datanema" << endl; */
                /* cout << hold.dataName << endl; */
                /* cout << "wholename" << endl; */
                /* cout << hold.wholeName << endl; */
                /* cout << "filetype" << endl; */
                /* cout << hold.fileType << endl; */
                dataList.push_back(hold);
                H5Dclose(did);
                break;
            case H5G_TYPE:
                cout << "A data type " << memb_name << " in group " << group_name << endl;
                break;
        }
    }
}

string H5File::getTrueGroupName(std::string groupName){
    string wholeGroupName;
    if (groupName == "" || groupName == "/") {
        wholeGroupName = "";
    }else if (groupName[0] != '/'){
        wholeGroupName = "/" + groupName;
    }else{
        wholeGroupName = groupName;
    }
    return wholeGroupName;
}

vector<dataset> H5File::getDatasetList(string groupName){
    hid_t file_id,group_id,dataset_id;

    /* openH5File(false); */
    /* openH5Group(groupName,false); */
    /* scanGroup("/"); */ 
    /* H5FGclose(); */
    return dataList;


}

vector<string> H5File::getGroupList(){
    return groupList;
}
