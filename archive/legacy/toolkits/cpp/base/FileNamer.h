#include <string>

#ifndef FileNamer_H
#define FileNamer_H
using namespace std;
class FileNamer{
    public:
        FileNamer();
        FileNamer(string);
        ~FileNamer();
        void setInName(string);
        string getInName();
        string autoNamer();
        string autoNamer(string);
        void setExtension(string);

    private:
        string inName;
        string outName;
        string extension;
        string shortName;
        string longName;
};
#endif
