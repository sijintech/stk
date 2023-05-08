#include <vector>
#include <string>
#ifndef DATA_H
#define DATA_H

using namespace std;
class Data{
    private:
        std::string fileName;
        int col;

    public:
        Data();
        ~Data();
        void initializeFile(std::vector<string>);
        void setFileName(std::string);
        std::string getFileName();
        void outputWithoutIndex(std::vector<double>);
        void outputWithIndex(int,std::vector<double>);
        void outputWithIndexAndName(int,std::string,std::vector<double>);
        void outputWithName(std::string,std::vector<double>);
        void outputWithPosition(std::vector<int>,std::vector<double>);


};
#endif
