#include <string>
#include <Data.h>
#ifndef VECTORDOMAIN_H
#define VECTORDOMAIN_H
#define piValue 3.141592653589
using namespace std;
class VectorDomain{
    protected:
        double domainStandardValue;
        double ** domainOrth;
        double ** domainRGB;
        double domainStandardAngleRad;
        int domainTypeCount;
        vector<string> domainTypeLabel;
        /* double * domainPercent; */

    public:
        VectorDomain(int);
        ~VectorDomain();
        double getStandardValue(); 
        void setStandardValue(double);
        double getStandardAngle();
        double getStandardRad();
        double getDomainR(int);
        double getDomainG(int);
        double getDomainB(int);
        void setStandardAngle(double);
        void setStandardRad(double);
        int getDomainType(double,double,double);
        int getDomainTypeCount();
        void setDomainTypeCount(int) ;
        void printDomainInfo();
        void printTestDat();
        string getDomainTypeLabel(int);
};
#endif
