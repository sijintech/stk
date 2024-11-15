#include <string>
#include <vector>

#ifndef SplittableString_H
#define SplittableString_H
using namespace std;
class SplittableString{
    public:
        SplittableString();
        SplittableString(std::string,std::string);
        ~SplittableString();

        void setDeliminator(std::string);
        void setText(std::string);
        std::string getBefore();
        std::string getAfter();
        std::string getText();
        std::string getFirst();
        std::string getLast();
        std::string getMiddle();
        std::string getIndex(int);
        vector<std::string> split();
        int getSize();


    private:
        std::string deliminator;
        std::string text;
        std::string before;
        std::string after;
        std::string first,last,middle;
        bool processed;
        vector<std::string> tagList;
};

#endif
