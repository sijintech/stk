#include <ScreenPrint.h>
#include <iostream>
#include <iomanip>
#include <stdio.h>
#include <string.h>

using namespace std;
ScreenPrint::ScreenPrint(){
    // width default to 120
    width = 120;
    columnWidth = 39;
    numberWidth = 12;
    numberPrecision = 4;
}
ScreenPrint::~ScreenPrint(){}

void ScreenPrint::setWidth(int widthIn){
    width = widthIn;
}

void ScreenPrint::setColumnWidth(int widthIn){
    columnWidth = widthIn;
}

void ScreenPrint::setNumberWidth(int widthIn){
    numberWidth = widthIn;
    numberPrecision = numberWidth-8;
    if (numberPrecision>4) {
        numberPrecision=4;
    }
}

int ScreenPrint::getWidth(){
    return width;
}

int ScreenPrint::getColumnWidth(){
    return columnWidth;
}

int ScreenPrint::getNumberWidth(){
    return numberWidth;
}

void ScreenPrint::printLeft(string outMessage,char fill){
    string messageHold;
    int messageWidth = 0,fillWidth = 0;
    messageWidth = outMessage.length();
    fillWidth = width - messageWidth - 1;
    cout << "|" << left << outMessage ;
    messageHold="|";
    cout << setfill(fill) << setw(fillWidth) << right << messageHold << endl;
}

void ScreenPrint::printLeft(const char* outMessage,char fill){
    string messageHold;
    int messageWidth = 0,fillWidth = 0;
    messageWidth = strlen(outMessage);
    fillWidth = width - messageWidth - 1;
    cout << "|" << left << outMessage ;
    messageHold="|";
    cout << setfill(fill) << setw(fillWidth) << right << messageHold << endl;
}

void ScreenPrint::printRight(string outMessage,char fill){
    int messageWidth = 0,fillWidth = 0;
    messageWidth = outMessage.length();
    fillWidth = width - messageWidth - 2;
    cout << "|" << right << setfill(fill) << setw(width-2) << outMessage ;
    cout << "|" << endl;
}

void ScreenPrint::printRight(const char* outMessage,char fill){
    int messageWidth = 0,fillWidth = 0;
    messageWidth = strlen(outMessage);
    fillWidth = width - messageWidth - 2;
    cout << "|" << right << setfill(fill) << setw(width-2) << outMessage ;
    cout << "|" << endl;
}

void ScreenPrint::printCenter(string outMessage,char fill){
    int messageWidth = 0,leftFillWidth = 0, rightFillWidth = 0;
    messageWidth = outMessage.length();
    rightFillWidth = (width - messageWidth - 2)/2;
    leftFillWidth = width - 2 - rightFillWidth;
    cout << "|" << right <<setfill(fill) << setw(leftFillWidth) << outMessage ;
    cout << setfill(fill) << setw(rightFillWidth) << fill ;
    cout << "|" << endl;
}

void ScreenPrint::printCenter(const char* outMessage,char fill){
    int messageWidth = 0,leftFillWidth = 0, rightFillWidth = 0;
    messageWidth = strlen(outMessage);
    rightFillWidth = (width - messageWidth - 2)/2;
    leftFillWidth = width - 2 - rightFillWidth;
    cout << "|" << right << setfill(fill) << setw(leftFillWidth) << outMessage ;
    cout << setfill(fill) << setw(rightFillWidth) << fill ;
    cout << "|" << endl;
}

void ScreenPrint::printError(string message){
    string outMessage;
    printCenter("---",'-');
    printCenter(" ",' ');
    outMessage = "                                                       000000000              ";   
    printCenter(outMessage,' ');
    outMessage = "           EEEEE   RRRR    RRRR     OOO    RRRR      00 x     x 00            ";
    printCenter(outMessage,' ');
    outMessage = "           E       R   R   R   R   O   O   R   R    0    x   x    0           ";
    printCenter(outMessage,' ');
    outMessage = "           E       R   R   R   R   O   O   R   R   0      x x      0          ";
    printCenter(outMessage,' ');
    outMessage = "           EEEEE   RRRR    RRRR    O   O   RRRR    0       x       0          ";
    printCenter(outMessage,' ');
    outMessage = "           E       R  R    R  R    O   O   R  R    0      x x      0          ";
    printCenter(outMessage,' ');
    outMessage = "           E       R   R   R   R   O   O   R   R    0    x   x    0           ";
    printCenter(outMessage,' ');
    outMessage = "           EEEEE   R   R   R   R    OOO    R   R     00 x     x 00            ";
    printCenter(outMessage,' ');
    outMessage = "                                                       000000000              ";
    printCenter(outMessage,' ');
    printCenter(" ",' ');
    printCenter(message,' ');
    printCenter(" ",' ');
    printCenter("---",'-');


}

void ScreenPrint::printError(const char* message){
    string outMessage;
    printCenter("---",'-');
    printCenter(" ",' ');
    outMessage = "                                                       000000000              ";   
    printCenter(outMessage,' ');
    outMessage = "           EEEEE   RRRR    RRRR     OOO    RRRR      00 x     x 00            ";
    printCenter(outMessage,' ');
    outMessage = "           E       R   R   R   R   O   O   R   R    0    x   x    0           ";
    printCenter(outMessage,' ');
    outMessage = "           E       R   R   R   R   O   O   R   R   0      x x      0          ";
    printCenter(outMessage,' ');
    outMessage = "           EEEEE   RRRR    RRRR    O   O   RRRR    0       x       0          ";
    printCenter(outMessage,' ');
    outMessage = "           E       R  R    R  R    O   O   R  R    0      x x      0          ";
    printCenter(outMessage,' ');
    outMessage = "           E       R   R   R   R   O   O   R   R    0    x   x    0           ";
    printCenter(outMessage,' ');
    outMessage = "           EEEEE   R   R   R   R    OOO    R   R     00 x     x 00            ";
    printCenter(outMessage,' ');
    outMessage = "                                                       000000000              ";
    printCenter(outMessage,' ');
    printCenter(" ",' ');
    printCenter(message,' ');
    printCenter(" ",' ');
    printCenter("---",'-');

}

void ScreenPrint::printVariable(const char* outMessage, bool outValue){
    cout << setfill(' ') << "|" << setw(columnWidth) << right << outMessage ;
    cout << " = " << setfill(' ') << setw(width-5-columnWidth) << left << boolalpha << outValue ;
    cout << "|" << endl;
}

void ScreenPrint::printVariable(const char* outMessage, int outValue){
    cout << setfill(' ') << "|" << setw(columnWidth) << right << outMessage ;
    cout << " = "  ;
    cout << left ;
    /* cout << setw(numberWidth) << outValue ; */
    cout << setfill(' ') << setw(width-5-columnWidth) << outValue ;
    cout << "|" << endl;
}

void ScreenPrint::printVariable(const char* outMessage, int outValue1, int outValue2){
    cout << setfill(' ') << "|" << setw(columnWidth) << right << outMessage ;
    cout << " = "  ;
    cout << left;
    cout << setw(numberWidth) << outValue1 ;
    /* cout << setw(numberWidth) << outValue2 ; */
    cout << setfill(' ') << setw(width-5-columnWidth-numberWidth*1) << outValue2;
    cout << "|" << endl;
}

void ScreenPrint::printVariable(const char* outMessage, int outValue1, int outValue2, int outValue3){
    cout << setfill(' ') << "|" << setw(columnWidth) << right << outMessage ;
    cout << " = "  ;
    cout << left ;
    cout << setw(numberWidth) << outValue1 ;
    cout << setw(numberWidth) << outValue2 ;
    /* cout << setw(numberWidth) << outValue3 ; */
    cout << setfill(' ') << setw(width-5-columnWidth-numberWidth*2) << outValue3 ;
    cout << "|" << endl;
}

void ScreenPrint::printVariable(const char* outMessage, double outValue){
    cout << setfill(' ') << "|" << setw(columnWidth) << right << outMessage ;
    cout << " = "  ;
    cout.precision(numberPrecision);
    cout << left << scientific ;
    /* cout << setw(numberWidth) << outValue ; */
    cout << setfill(' ') << setw(width-5-columnWidth) << outValue ;
    cout << "|" << endl;
}

void ScreenPrint::printVariable(const char* outMessage, double outValue1, double outValue2){
    cout << setfill(' ') << "|" << setw(columnWidth) << right << outMessage ;
    cout << " = "  ;
    cout.precision(numberPrecision);
    cout << left << scientific ;
    cout << setw(numberWidth) << outValue1 ;
    /* cout << setw(numberWidth) << outValue2 ; */
    cout << setfill(' ') << setw(width-5-columnWidth-numberWidth*1) << outValue2 ;
    cout << "|" << endl;
}

void ScreenPrint::printVariable(const char* outMessage, double outValue1, double outValue2, double outValue3){
    cout << setfill(' ') << "|" << setw(columnWidth) << right << outMessage ;
    cout << " = "  ;
    cout.precision(numberPrecision);
    cout << left << scientific ;
    cout << setw(numberWidth) << outValue1 ;
    cout << setw(numberWidth) << outValue2 ;
    /* cout << setw(numberWidth) << outValue3 ; */
    cout << setfill(' ') << setw(width-5-columnWidth-numberWidth*2) << outValue3;
    cout << "|" << endl;
}

void ScreenPrint::printVariable(const char* outMessage, double outValue1, double outValue2, double outValue3, double outValue4, double outValue5){
    cout << setfill(' ') << "|" << setw(columnWidth) << right << outMessage ;
    cout << " = "  ;
    cout.precision(numberPrecision);
    cout << left << scientific ;
    cout << setw(numberWidth) << outValue1 ;
    cout << setw(numberWidth) << outValue2 ;
    cout << setw(numberWidth) << outValue3 ;
    cout << setw(numberWidth) << outValue4 ;
    /* cout << setw(numberWidth) << outValue5 ; */
    cout << setfill(' ') << setw(width-5-columnWidth-numberWidth*4) << outValue5;
    cout << "|" << endl;
}

void ScreenPrint::printVariable(const char* outMessage, const char* outValue){
    cout << setfill(' ') << "|" << setw(columnWidth) << right << outMessage ;
    cout << " = " << setfill(' ') << setw(width-5-columnWidth) << left << outValue ;
    cout << "|" << endl;
}

void ScreenPrint::printVariable(const char* outMessage, string outValue){
    cout << setfill(' ') << "|" << setw(columnWidth) << right << outMessage ;
    cout << " = " << setfill(' ') << setw(width-5-columnWidth) << left << outValue ;
    cout << "|" << endl;
}
