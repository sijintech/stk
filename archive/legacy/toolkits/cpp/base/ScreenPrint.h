/* This is header for screen printing class */
#include <string>
#ifndef SCREENPRINT_H
#define SCREENPRINT_H

using namespace std;
class ScreenPrint{
    private:
        int width;
        int columnWidth;
        int numberWidth;
        int numberPrecision;
    public:
        ScreenPrint();
        ~ScreenPrint();
        void setWidth(int width);
        void setColumnWidth(int columnWidth);
        void setNumberWidth(int columnWidth);
        int getColumnWidth();
        int getNumberWidth();
        int getWidth();
        void printError(string);
        void printError(const char*);
        void printLeft(string,char);
        void printLeft(const char*,char);
        void printCenter(string,char);
        void printCenter(const char*,char);
        void printRight(string,char);
        void printRight(const char*,char);
        void printVariable(const char*,bool);
        void printVariable(const char*,int);
        void printVariable(const char*,int,int);
        void printVariable(const char*,int,int,int);
        void printVariable(const char*,double);
        void printVariable(const char*,double,double);
        void printVariable(const char*,double,double,double);
        void printVariable(const char*,double,double,double,double,double);
        void printVariable(const char*,string);
        void printVariable(const char*,const char*);
};
#endif
