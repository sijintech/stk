#include <SplittableString.h>
#include <iostream>
using namespace std;

SplittableString::SplittableString(){
    deliminator=".";
    text="";
    before="";
    after="";
    first="";
    last="";
    middle="";
    processed=false;
}

SplittableString::~SplittableString(){
}



SplittableString::SplittableString(string textIn,string delimIn){
    text=textIn;
    deliminator=delimIn;
    first="";
    middle="";
    last="";
    before="";
    after="";
    processed=false;
    tagList.clear();
    split();
}

void SplittableString::setDeliminator(std::string newDeliminator){
    deliminator = newDeliminator;
    tagList.clear();
    /* split(text,deliminator); */
}

void SplittableString::setText(std::string newText){
    text=newText;
    tagList.clear();
    /* split(text,deliminator); */
}


string SplittableString::getBefore(){
    return before;
}

string SplittableString::getAfter(){
    return after;
}

string SplittableString::getText(){
    return text;
}

string SplittableString::getFirst(){
    return first;
}

string SplittableString::getLast(){
    return last;
}

string SplittableString::getMiddle(){
    return middle;
}

string SplittableString::getIndex(int index){
    if (index<0) {
        index=0;
    }
    if (index>tagList.size()) {
        index=tagList.size(); 
    }
    return tagList[index];
}

int SplittableString::getSize(){
  return tagList.size();
}
vector<std::string> SplittableString::split(){
    if (!processed) {
        string textHold;
        std::size_t found = text.find(deliminator);
        if(found!=std::string::npos){
            before=text.substr(0,found);
            after=text.substr(found+1);
        }else{
            before=text;
            after="";
        }

        textHold=text;

        found = textHold.find(deliminator);
        while(found!=std::string::npos){
            /* std::cout << "inside split " << processed << " " << found << " " << textHold<< endl; */
            tagList.push_back(text.substr(0,found));
            textHold=textHold.substr(found+1);
            found = textHold.find(deliminator);
        }
        tagList.push_back(textHold);


        first=text.substr(0,text.find_first_of(deliminator));
        last=text.substr(text.find_last_of(deliminator)+1);
        middle=text.substr(text.find_first_of(deliminator)+1,text.find_last_of(deliminator)-text.find_first_of(deliminator)-1);
        /* std::cout << "split " << first << " " << last << " " << middle << endl; */
        processed=true;
    }

    return tagList;
}
