#include <string>
#include <SplittableString.h>

#ifndef FreeFormatOneLine_H
#define FreeFormatOneLine_H
using namespace std;
class FreeFormatOneLine{
    public:
        FreeFormatOneLine();
        FreeFormatOneLine(string);
        ~FreeFormatOneLine();

        void setText(string);
        void setCommentDeliminator(string);
        void setAssignDeliminator(string);
        void setSecondLevelDeliminator(string);
        void split();
        string getFirstLevelIdentifier();
        string getSecondLevelIdentifier();
        string getValues();
        string getComment();


    private:
        string commentDeliminator;
        string assignDeliminator;
        string secondLevelDeliminator;
        string comment;
        string text;
        string firstLevelIdentifier;
        string secondLevelIdentifier;
        string values;
        string trim(const string& str);

};
#endif
