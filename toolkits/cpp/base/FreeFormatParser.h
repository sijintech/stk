#include <string>
#include <FreeFormatOneLine.h>
#include <vector>


#ifndef FreeFormatParser_H
#define FreeFormatParser_H
using namespace std;
class FreeFormatParser{
    public:
        FreeFormatParser();
        FreeFormatParser(string);
        ~FreeFormatParser();
        void setFilename(string);
        bool parse();
        vector<string> getFirstLevel(string firstLevelName);
        vector<string> getFirstLevel(int index);
        void setFirstWhole(vector<vector<string>>);
        void setSecondWhole(vector<vector<string>>);
        void write(string);
        vector<string> getSecondLevel(int index);
        vector<string> getSecondLevel(string firstLevelName,string secondLevelName);
        vector<vector<string> > getFirstWhole();
        vector<vector<string> > getSecondWhole();
        bool firstKeyExist(string firstLevelName);
        bool secondKeyExist(string firstLevelName,string secondLevelName);
        int getFirstLevelLength();
        int getSecondLevelLength();
        template <typename T>
        vector<fileGroup> readKeyword(string keyword);
        vector<fileGroup> readKeyword(string keyword);

    private:
        string filename;
        vector<vector<string> > firstLevel;
        vector<vector<string> > secondLevel;
        int firstLevelLength;
        int secondLevelLength;

};
#endif
