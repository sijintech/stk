#include "nmathbasic/exprtk.hpp"
#include <string.h>
#include <iostream>

exprtk::symbol_table<double> symbol_table_double;
exprtk::expression<double> expression_double;
exprtk::parser<double> parser_double;



extern"C" void addvariable_(char *name,int *length,double *value){
    //std::string nameString(name);
    int i=0;
    std::string output("");
   i=0;
    if(name!=NULL){
        if(name[0]!='\0'){
        while(i<*length){
            output+=name[i];
            i++;
        }
        }
    }


    if(symbol_table_double.symbol_exists(output)){
      symbol_table_double.remove_variable(output);
      symbol_table_double.clear_variables() ;
    }
    symbol_table_double.add_variable(output,*value);

     //std::cout << "inside:" << name <<"||"<<strlen(name)<<"||"<< *value <<std::endl; ;  
     //std::cout << "inside add variable:" << output <<"||"<<output.length()<<"||"<< *value <<std::endl; ;  
}

extern"C" void addconstant_(char *name,int *length,double *value){
    //std::string nameString(name);
    int i=0;
    std::string output("");
   i=0;
    if(name!=NULL){
        if(name[0]!='\0'){
        while(i<*length){
            output+=name[i];
            i++;
        }
        }
    }


    symbol_table_double.add_constant(output,*value);
    /* std::cout << "inside:" << name <<"||"<<strlen(name)<<"||"<< *value <<std::endl; ; */ 
    /* std::cout << "inside:" << output <<"||"<<output.length()<<"||"<< *value <<std::endl; ; */ 
}
extern"C" void evaluate_(double *result,char *expression_string,int *length){
    //std::string expressionString(expression_string);
    int i=0;
    std::string output("");
   i=0;
    if(expression_string!=NULL){
        if(expression_string[0]!='\0'){
        while(i<*length){
            output+=expression_string[i];
            i++;
        }
        }
    }


    expression_double.register_symbol_table(symbol_table_double);
    parser_double.compile(output,expression_double);
    //parser_double.compile("1*2*3",expression_double);
    *result = expression_double.value();
    /* std::cout << "evaluate:" << *result << "[" <<expression_string <<"]"<<output<<"|"<<std::endl;; */
}
