#include <FreeFormatOneLine.h>
using namespace std;

FreeFormatOneLine::FreeFormatOneLine(){
    commentDeliminator = "#";
    assignDeliminator = "=";
    secondLevelDeliminator = ".";
    comment = "";
    firstLevelIdentifier = "";
    secondLevelIdentifier = "";
    values = "";
}

FreeFormatOneLine::~FreeFormatOneLine(){
}


FreeFormatOneLine::FreeFormatOneLine(string textIn){
    commentDeliminator = "#";
    assignDeliminator = "=";
    secondLevelDeliminator = ".";
    comment = "";
    firstLevelIdentifier = "";
    secondLevelIdentifier = "";
    values = "";
   text = textIn;  
}

string FreeFormatOneLine::trim(const string& str){
    size_t first=str.find_first_not_of(' ');
    if(string::npos == first){
        return str;
    }
    size_t last=str.find_last_not_of(' ');
    return str.substr(first,(last-first+1));
}


void FreeFormatOneLine::split(){
    string textString,identifier;

    SplittableString wholeText(text,commentDeliminator);
    /* wholeText.split(); */
    textString = wholeText.getBefore();
    comment = wholeText.getAfter();
    comment = trim(comment.c_str());

    SplittableString beforeComment(textString,assignDeliminator);
    /* beforeComment.split(); */
    values = beforeComment.getAfter();
    values = trim(values.c_str());
    identifier = beforeComment.getBefore();

    SplittableString beforeAssign(identifier,secondLevelDeliminator);
    firstLevelIdentifier = beforeAssign.getBefore();
    firstLevelIdentifier = trim(firstLevelIdentifier.c_str());
    secondLevelIdentifier = beforeAssign.getAfter();
    secondLevelIdentifier = trim(secondLevelIdentifier.c_str());

}

void FreeFormatOneLine::setText(string textIn){
    text=textIn;
}

void FreeFormatOneLine::setCommentDeliminator(string delim){
    commentDeliminator=delim;
}

void FreeFormatOneLine::setAssignDeliminator(string delim){
    assignDeliminator=delim;
}

void FreeFormatOneLine::setSecondLevelDeliminator(string delim){
    secondLevelDeliminator=delim;
}


string FreeFormatOneLine::getFirstLevelIdentifier(){
    return firstLevelIdentifier;
}

string FreeFormatOneLine::getSecondLevelIdentifier(){
    return secondLevelIdentifier;
}

string FreeFormatOneLine::getValues(){
    return values;
}

string FreeFormatOneLine::getComment(){
    return comment;
}
