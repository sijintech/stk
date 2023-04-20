#ifndef __NTEXTUTILS_HPP__
#define __NTEXTUTILS_HPP__


#include <string>
#include <vector>
#include <sstream>
#include "ntextutils.h"

char * string2char(std::string input);
std::string char2string(char *input);
std::vector<std::string> NStringArray2string_vector(NStringArray* input);
NStringArray* string_vector2NStringArray(std::vector<std::string> input);
std::string trim(std::string const&str);
std::string n_string_trim_rightpp(std::string s, const char* t = " \t\n\r\f\v");
std::string n_string_trim_rightpp(std::string s, const char* t = " \t\n\r\f\v");
std::string n_string_trim_leftpp(std::string s, const char* t = " \t\n\r\f\v");
std::vector<std::string> n_string_splitpp(std::string versionNumber,const char* delim);
std::string n_file_read_stringpp(std::string filename);
std::string join_cpp(std::string a,std::string b, std::string delim);
std::string join_cpp(std::vector<std::string> toJoin,std::string delim);
int n_string_equalpp(std::vector<std::string> a, std::string b);
int contain_cpp(std::vector<std::string> a, std::string b);

char * string2char(std::string input){
    int length=0;
    if(input[input.length()-1]=='\0'){
        length=input.length();
    }else{
        length=input.length()+1;
    }
    char * output=new char[length];
    strcpy(output,input.c_str());
    return output;
}

std::string char2string(char *input){
    std::string output("");
    int length=0;
    if(input!= NULL ){
        if(input[0]!='\0'){
            while(int(input[length])>0){
                output+=input[length];
                length++;
            }
        }
    }
    return output;
}

std::vector<std::string> NStringArray2string_vector(NStringArray* input){
    std::vector<std::string> output;
    for (size_t i = 0; i < input->length; i++)
    {
        output.push_back(char2string(input->data[i].data));
    }
    return output;
}

// This is clearly wrong, needs to be corrected in the future
NStringArray* string_vector2NStringArray(std::vector<std::string> input){
    NStringArrayPtr output;
    output->length=input.size();
    for (size_t i = 0; i < output->length; i++)
    {
        strcpy(output->data[i].data,string2char(input[i]));
    }
    return output;
}

// trim from end of string (right)
std::string n_string_trim_rightpp(std::string s, const char* t = " \t\n\r\f\v")
{
    char *out=string2char(s);
    out=n_string_trim_right(out,t);
    return char2string(out);
}

// trim from beginning of string (left)
std::string n_string_trim_leftpp(std::string s, const char* t = " \t\n\r\f\v")
{
    char *out=string2char(s);
    out=n_string_trim_left(out,t);
    return char2string(out);
}

// trim from both ends of string (right then left)
std::string both_trim(std::string s, const char* t = " \t\n\r\f\v")
{
    return n_string_trim_leftpp(n_string_trim_rightpp(s, t), t);
}

// std::vector<std::string> n_string_splitpp(char *versionNumber,const char delim);

std::vector<std::string> n_string_splitpp(std::string input,const char *delim){
    std::vector<std::string> output;
    char *inputChar = string2char(input);
    NStringArray* nsa=n_string_split(inputChar,delim);
    output = NStringArray2string_vector(nsa);
    return output;
}

std::string n_file_read_stringpp(std::string filename){
    std::string output;
    char *file=string2char(filename);
    size_t *size;
    int *err;
    char *outchar;
    outchar=n_file_read_string(file,size,err);
    output=char2string(outchar);
    return output;
}

std::string join_string_cpp(std::string a,std::string b, std::string delim){
    const char *a_char=string2char(a);
    const char *b_char=string2char(b);
    const char *delim_char=string2char(delim);
    char *out;
    out=n_string_join(a_char,b_char,delim_char);
    return char2string(out);
}

std::string join_vector_cpp(std::vector<std::string> toJoin,std::string delim){
    NStringArrayPtr toJ = string_vector2NStringArray(toJoin);
    std::string output;
    output=char2string(n_NStringArray_join(toJ,string2char(delim)));
    return output;
}

int n_string_equalpp(std::vector<std::string> a, std::string b){
    return n_string_equal(string2char(a),string2char(b));
}

int contain_cpp(std::vector<std::string> a, std::string b){
    return contain_c(string_vector2NStringArray(a),string2char(b));
}

// int compareAinB(std::string A, std::vector<std::string> B);

// int compareAB(std::string A, std::string B);

// int compareAB(std::vector<std::string> A,std::vector<std::string> B);





#endif __NTEXTUTILS_HPP__