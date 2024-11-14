#include "niobasic/timeFile.h"


void n_timeFile_write_line_from_NStringArray(NStringArray header, const char *file){
    FILE *fp = fopen(file,"a");
    NString out=n_NStringArray_join(header,SEPARATOR);
    fprintf(fp,"%s \n",out.data);
    fclose(fp);
}

void n_timeFile_write_line_from_double_f(double **input, int *length, const char *file){
    n_timeFile_write_line_from_double(*input, *length, file);
}

void n_timeFile_write_line_from_double(double *input, int length, const char *file){
    NStringArray temp=n_double_to_NStringArray(input,length,"%.8e");
    n_timeFile_write_line_from_NStringArray(temp,file);
}

void n_timeFile_write_line_from_string_f(const char *header, const char *file){
    n_timeFile_write_line_from_string(header,file);
}

void n_timeFile_write_line_from_string(const char *header, const char *file){
    NStringArray temp=n_string_split(header,SEPARATOR);
    n_timeFile_write_line_from_NStringArray(temp,file);
}

void n_timeFile_write_header_line_f(const char *header, const char *file){
    n_timeFile_write_header_line(header,file);
}

void n_timeFile_write_header_line(const char *header, const char *file){
    remove(file);
    NStringArray temp=n_string_split(header,SEPARATOR);
    n_timeFile_write_line_from_NStringArray(temp,file);
}

double * n_timeFile_read(double *output, const char *headerName, const char *file){
    // char *line=NULL;
    char line[MAX_STRING]={'\0'};
    // size_t len=0;
    NStringArray temp;
    int index=0,i=0;

    FILE *fp = fopen(file,"r");
    // getline(&line,&len,fp);
    fgets(line,MAX_STRING,fp);
    temp=n_string_split(line,SEPARATOR);
    index=n_NStringArray_string_index(temp,headerName);
    // while (getline(&line, &len, fp) != -1) {
    while (fgets(line,MAX_STRING,fp)!=NULL) {
        temp=n_string_split(line,SEPARATOR);
        sscanf(temp.data[index],"%lf",&output[i]);
        i++;
    }
    fclose(fp);
    // free(line);
    return output;
}
