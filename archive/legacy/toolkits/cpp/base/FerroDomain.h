#include <string>
#include <VectorDomain.h>
#ifndef FERRODOMAIN_H
#define FERRODOMAIN_H
#define piValue 3.141592653589
class FerroDomain:public VectorDomain{
    private:
//        double ** domainOrth;
//        double ** domainRGB;
//        double domainStandardAngleRad;
        /* double * domainPercent; */

    public:
        FerroDomain();
        ~FerroDomain();
//        double getStandardValue(); 
//        void setStandardValue(double);
//        double getStandardAngle();
//        double getStandardRad();
//        double getDomainR(int);
//        double getDomainG(int);
//        double getDomainB(int);
//        void setStandardAngle(double);
//        void setStandardRad(double);
//        int getDomainType(double,double,double);
};
#endif
