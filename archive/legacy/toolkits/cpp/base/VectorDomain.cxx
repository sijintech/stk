#include <VectorDomain.h>
#include <cmath>
#include <iostream>
#include <sstream>


using namespace std;
VectorDomain::VectorDomain(int length):domainTypeCount(length){
   domainOrth=new double*[domainTypeCount];
   domainRGB=new double*[domainTypeCount];
   /* domainPercent = new double[27]; */
   for (int i = 0; i < domainTypeCount; i++) {
       domainRGB[i] = new double[3];
       domainOrth[i] = new double[3];
       domainTypeLabel.push_back("Label_"+std::to_string(i));
       /* domainPercent[i] = 0; */
   }

    // domainRGB[0][0]=0.752912;domainRGB[0][1]=0.752912;domainRGB[0][2]=0.752912; //sub
    // domainRGB[1][0]=0;domainRGB[1][1]=0;domainRGB[1][2]=1;  //R1+
    // domainRGB[2][0]=0.46;domainRGB[2][1]=0.7175;domainRGB[2][2]=0.8135; //R1-
    // domainRGB[3][0]=0;domainRGB[3][1]=0.1537870;domainRGB[3][2]=0.0; //R2+
    // domainRGB[4][0]=0;domainRGB[4][1]=1;domainRGB[4][2]=0; //R2-
    // domainRGB[5][0]=1;domainRGB[5][1]=0;domainRGB[5][2]=0; //R3+
    // domainRGB[6][0]=1;domainRGB[6][1]=0.566921;domainRGB[6][2]=0.633741; //R3-
    // domainRGB[7][0]=1;domainRGB[7][1]=0.418685;domainRGB[7][2]=0; //R4+
    // domainRGB[8][0]=1;domainRGB[8][1]=1;domainRGB[8][2]=0; //R4-
    // domainRGB[9][0]=1;domainRGB[9][1]=0;domainRGB[9][2]=1; //O1+
    // domainRGB[10][0]=0.64629;domainRGB[10][1]=0.130165;domainRGB[10][2]=0.130165; //O1-
    // domainRGB[11][0]=0.9;domainRGB[11][1]=0.566921;domainRGB[11][2]=0.633741; //O2+
    // domainRGB[12][0]=0.751111;domainRGB[12][1]=0.393695;domainRGB[12][2]=0.751111; //O2-
    // domainRGB[13][0]=0.418685;domainRGB[13][1]=0.027128;domainRGB[13][2]=0.027128; //O3+
    // domainRGB[14][0]=0.678201;domainRGB[14][1]=0.498270;domainRGB[14][2]=0.301423; //O3-
    // domainRGB[15][0]=0.476371;domainRGB[15][1]=0.035432;domainRGB[15][2]=0.14173; //O4+
    // domainRGB[16][0]=0.961169;domainRGB[16][1]=0.251965;domainRGB[16][2]=0.199862; //O4-
    // domainRGB[17][0]=0.355309;domainRGB[17][1]=0.968874;domainRGB[17][2]=0.355309; //O5+
    // domainRGB[18][0]=0.038446;domainRGB[18][1]=0.646290;domainRGB[18][2]=0.038446; //O5-
    // domainRGB[19][0]=0.766921;domainRGB[19][1]=0.766921;domainRGB[19][2]=0.766921; //O6+
    // domainRGB[20][0]=0.169550;domainRGB[20][1]=0.169550;domainRGB[20][2]=0.169550; //O6-
    // domainRGB[21][0]=0.566921;domainRGB[21][1]=0.566921;domainRGB[21][2]=0.566921; //a1+
    // domainRGB[22][0]=0.393695;domainRGB[22][1]=0.015747;domainRGB[22][2]=0.885813; //a1-
    // domainRGB[23][0]=0.0;domainRGB[23][1]=0.0;domainRGB[23][2]=0.0; //a2+
    // domainRGB[24][0]=1.0;domainRGB[24][1]=0.710881;domainRGB[24][2]=0.0; //a2-
    // domainRGB[25][0]=0.885813;domainRGB[25][1]=0.813533;domainRGB[25][2]=0.301423; //c+
    // domainRGB[26][0]=0.8867188;domainRGB[26][1]=0.4335937;domainRGB[26][2]=0.0273438; //c-
    //
    // domainOrth[0][0] = 0;domainOrth[0][1]=0;domainOrth[0][2]=0;
    // domainOrth[1][0] = 1/std::sqrt(3);domainOrth[1][1]=1/std::sqrt(3);domainOrth[1][2]=1/std::sqrt(3);
    // domainOrth[2][0] = -1/std::sqrt(3);domainOrth[2][1]=-1 / std::sqrt(3);domainOrth[2][2]=-1 / std::sqrt(3);
    // domainOrth[3][0] = -1 / std::sqrt(3);domainOrth[3][1]=1/std::sqrt(3);domainOrth[3][2]=1/std::sqrt(3);
    // domainOrth[4][0] = 1/std::sqrt(3);domainOrth[4][1]=-1 / std::sqrt(3);domainOrth[4][2]=-1 / std::sqrt(3);
    // domainOrth[5][0] = -1 / std::sqrt(3);domainOrth[5][1]= -1 / std::sqrt(3);domainOrth[5][2]=1/std::sqrt(3);
    // domainOrth[6][0] = 1/std::sqrt(3);domainOrth[6][1]=1/std::sqrt(3);domainOrth[6][2]=-1 / std::sqrt(3) ;
    // domainOrth[7][0] = 1/std::sqrt(3);domainOrth[7][1]=-1 / std::sqrt(3);domainOrth[7][2]=1/std::sqrt(3) ;
    // domainOrth[8][0] = -1 / std::sqrt(3);domainOrth[8][1]=1/std::sqrt(3);domainOrth[8][2]=-1 / std::sqrt(3);
    // domainOrth[9][0] =  1/std::sqrt(2);domainOrth[9][1]=1/std::sqrt(2);domainOrth[9][2]=0;
    // domainOrth[10][0]= -1 / std::sqrt(2);domainOrth[10][1]-1 / std::sqrt(2);domainOrth[10][2]=0;
    // domainOrth[11][0]= 1/std::sqrt(2);domainOrth[11][1]-1 / std::sqrt(2);domainOrth[11][2]=0;
    // domainOrth[12][0]= -1 / std::sqrt(2);domainOrth[12][1]=1/std::sqrt(2);domainOrth[12][2]=0;
    // domainOrth[13][0]= 1/std::sqrt(2);domainOrth[13][1]=0;domainOrth[13][2]=1/std::sqrt(2);
    // domainOrth[14][0]= -1 / std::sqrt(2);domainOrth[14][1]=0;domainOrth[14][2]=-1 / std::sqrt(2) ;
    // domainOrth[15][0]= 1/std::sqrt(2);domainOrth[15][1]=0;domainOrth[15][2]=-1 / std::sqrt(2) ;
    // domainOrth[16][0]= -1 / std::sqrt(2);domainOrth[16][1]=0;domainOrth[16][2]=1/std::sqrt(2) ;
    // domainOrth[17][0]=0;domainOrth[17][1]=1/std::sqrt(2);domainOrth[17][2]=1/std::sqrt(2);
    // domainOrth[18][0]=0;domainOrth[18][1]=-1 / std::sqrt(2);domainOrth[18][2]=-1 / std::sqrt(2) ;
    // domainOrth[19][0]=0;domainOrth[19][1]=1/std::sqrt(2);domainOrth[19][2]=-1 / std::sqrt(2) ;
    // domainOrth[20][0]=0;domainOrth[20][1]=-1 / std::sqrt(2);domainOrth[20][2]=1/std::sqrt(2) ;
    // domainOrth[21][0]=1;domainOrth[21][1]=0;domainOrth[22][2]=0;
    // domainOrth[22][0]=-1;domainOrth[22][1]=0;domainOrth[22][2]=0;
    // domainOrth[23][0]=0;domainOrth[23][1]=1;domainOrth[23][2]=0;
    // domainOrth[24][0]=0;domainOrth[24][1]=-1;domainOrth[24][2]=0;
    // domainOrth[25][0]=0;domainOrth[25][1]=0;domainOrth[25][2]=1;
    // domainOrth[26][0]=0;domainOrth[26][1]=0;domainOrth[26][2]=-1;
    }


VectorDomain::~VectorDomain(){
    /* delete [] domainOrth; */
    /* delete [] domainRGB; */
}

int VectorDomain::getDomainType(double px,double py,double pz){
   double cosValue=0,angle=0,length=0;
   double hold=piValue;
   int domainValue=-1;

   /* cout << "Process domain type for "<< px << " " << py << " " << pz << " " << domainStandardAngleRad<< endl; */
   length=std::sqrt(px*px+py*py+pz*pz);
   if(length>domainStandardValue){

       for (int i = 0; i < domainTypeCount; i++) {
          cosValue = (px*domainOrth[i][0]+py*domainOrth[i][1]+pz*domainOrth[i][2])/length;
          if (cosValue>1) {
              angle=0;
          }else if (cosValue<-1) {
              angle=piValue;
          }else{
              angle=std::acos(cosValue);
          }

          /* cout << "in loop "<< i << " " << cosValue << " " << angle << " " << hold << " " << domainOrth[i][0] << " " << domainOrth[i][1] << " " << domainOrth[i][2] << endl; */
          if (angle<domainStandardAngleRad && angle < hold) {
              hold=angle;
              domainValue=i;
          }
       }
   }

   /* cout << "Returning the domain type is "<< domainValue << endl; */


   return domainValue;
}

double VectorDomain::getDomainR(int index){
   return domainRGB[index][0];
}

double VectorDomain::getDomainG(int index){
   return domainRGB[index][1];
}

double VectorDomain::getDomainB(int index){
   return domainRGB[index][2];
}

void VectorDomain::setStandardValue(double value){
   domainStandardValue=value;
}

void VectorDomain::setStandardAngle(double angle){
   domainStandardAngleRad=angle/180*piValue;
}

void VectorDomain::setStandardRad(double rad){
   domainStandardAngleRad=rad;
}

int VectorDomain::getDomainTypeCount(){
  return domainTypeCount;
}

void VectorDomain::printDomainInfo(){
    Data domain;
    vector<string> header(8);
    vector<double> value(6);
    domain.setFileName("Vector_Domain.txt");
    header[0] = "Domain index";
    header[1] = "Domain label";
    header[2] = "Component X";
    header[3] = "Component Y";
    header[4] = "Component Z";
    header[5] = "Color R";
    header[6] = "Color G";
    header[7] = "Color B";
    domain.initializeFile(header);
    for (int i = 0; i < domainTypeCount; i++) {
        value[0] = domainOrth[i][0];
        value[1] = domainOrth[i][1];
        value[2] = domainOrth[i][2];
        value[3] = domainRGB[i][0];
        value[4] = domainRGB[i][1];
        value[5] = domainRGB[i][2];
       domain.outputWithIndexAndName(i,domainTypeLabel[i],value); 
    }
}

void VectorDomain::printTestDat(){
     Data domain;
    vector<string> header(8);
    vector<double> value(6);
    vector<int> POS(3);
    domain.setFileName("test.test");
    header[0] = "1";
    header[1] = "1";
    stringstream ss;
    ss<<domainTypeCount+10;
    header[2] = ss.str();;
    domain.initializeFile(header);
    for (int i = 0; i < 5; i++) {
        POS[0]=1;
        POS[1]=1;
        POS[2]=i+1;
        value[0]=0;
        value[1]=0;
        value[2]=0;
        value[3]=0;
        value[4]=0;
        value[5]=0;
       domain.outputWithPosition(POS,value); 
    }
    for (int i = 5; i < domainTypeCount+5; i++) {
        POS[0] = 1;
        POS[1] = 1;
        POS[2] = i+1;
        value[0] = domainOrth[i-5][0];
        value[1] = domainOrth[i-5][1];
        value[2] = domainOrth[i-5][2];
        value[3] = domainOrth[i-5][0];
        value[4] = domainOrth[i-5][1];
        value[5] = domainOrth[i-5][2];
       domain.outputWithPosition(POS,value); 
    }
    for (int i = domainTypeCount+5; i < domainTypeCount+10; i++) {
        POS[0]=1;
        POS[1]=1;
        POS[2]=i+1;
        value[0]=0;
        value[1]=0;
        value[2]=0;
        value[3]=0;
        value[4]=0;
        value[5]=0;
       domain.outputWithPosition(POS,value); 
    }

   
}

std::string VectorDomain::getDomainTypeLabel(int index){
    return domainTypeLabel[index];
}
