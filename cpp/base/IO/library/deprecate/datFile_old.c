#include "niobasic/datFile_old.h"

// Double precision
DatPtr_4D_double Dat_4D_double_init(int x, int y, int z, int component){
    DatPtr_4D_double data;
    data = malloc(sizeof(Dat_4D_double));
    memset(data,0,sizeof(Dat_4D_double));
    data->dim1=x;
    data->dim2=y;
    data->dim3=z;
    data->component=component;
    // data->data=(double**)malloc(sizeof(double*));
    data->data=(double*)malloc(sizeof(double)*x*y*z*component);
    // memset(temp,0, sizeof(double)*x*y*z*component);
    for (size_t i = 0; i < x*y*z*component; i++)
    {
        data->data[i]=0;
    }
    return data;
}

void Dat_4D_double_free(DatPtr_4D_double data){
    free(data->data);
    free(data);
}

double Dat_4D_double_get(const DatPtr_4D_double data, const int i, const int j, const int k, const int l){
    return data->data[i*data->component*data->dim3*data->dim2+j*data->component*data->dim3+k*data->component+l];
}

void Dat_4D_double_set(DatPtr_4D_double data, const int i, const int j, const int k, const int l, double x){
    // ZF_LOGD("xyz: %i, %i, %i, %i, %lf",i,j,k,l,x);
    data->data[i*data->component*data->dim3*data->dim2+j*data->component*data->dim3+k*data->component+l]=x;
}

void DatFile_4D_double_read(DatPtr_4D_double data, const char *file){
    FILE *fp = fopen(file,"r");
    char *line=NULL;
    size_t len=0;
    ssize_t read;
    double temp;
    int x,y,z;
    // First line of the file is for dimensions
    // getline(&line,&len,fp);
    fscanf(fp,"%i %i %i",&x,&y,&z);
    // ZF_LOGD("debug %i %i %i",x,y,z);

    // ZF_LOGD("file: %p, %p, %p, %p, %p",data,&data->data, data->data, &data->data[0], &data->data[1]);
    data->dim1 = x;
    data->dim2 = y;
    data->dim3 = z;
    size_t lineCount=x*y*z;
    for (size_t count = 0; count < lineCount; count++){
        fscanf(fp,"%i %i %i",&x,&y,&z);
        for (size_t i = 0; i < data->component; i++)
        {
            fscanf(fp,"%lf",&temp);
            // ZF_LOGD("double:  %i %i %i %lf",x,y,z,temp);
            Dat_4D_double_set(data,x-1,y-1,z-1,i,temp);
            // ZF_LOGD("afterward: %lf",data->data[count]);
        }
    }
    fclose(fp);
}

void DatFile_4D_double_write(DatPtr_4D_double data, const char *file){
    FILE *fp = fopen(file,"w");
    char *line=NULL;
    size_t len=0;
    ssize_t read;
    // First line of the file is for dimensions
    fprintf(fp,"%li %li %li \n",data->dim1,data->dim2,data->dim3);
    for (size_t i = 0; i < data->dim1; i++){
        for (size_t j = 0; j < data->dim2; j++){
            for (size_t k = 0; k < data->dim3; k++){
                fprintf(fp,"%li %li %li ",i+1,j+1,k+1);
                for (size_t l = 0; l < data->component; l++){
                    fprintf(fp,"%f ",Dat_4D_double_get(data,i,j,k,l));
                }
                fprintf(fp,"\n");
            }
        }
    }
    fclose(fp);
    if(line)free(line);
}

// Integer
DatPtr_4D_int Dat_4D_int_init(int x, int y, int z, int component){
    DatPtr_4D_int data;
    data = malloc(sizeof(Dat_4D_int));
    memset(data,0,sizeof(Dat_4D_int));
    data->dim1=x;
    data->dim2=y;
    data->dim3=z;
    data->component=component;
    // data->data=(int**)malloc(sizeof(int*));
    data->data=(int*)malloc(sizeof(int)*x*y*z*component);
    // memset(temp,0, sizeof(int)*x*y*z*component);
    for (size_t i = 0; i < x*y*z*component; i++)
    {
        data->data[i]=0;
    }
    return data;
}

void Dat_4D_int_free(DatPtr_4D_int data){
    free(data->data);
    free(data);
}

int Dat_4D_int_get(const DatPtr_4D_int data, const int i, const int j, const int k, const int l){
    return data->data[i*data->component*data->dim3*data->dim2+j*data->component*data->dim3+k*data->component+l];
}

void Dat_4D_int_set(DatPtr_4D_int data, const int i, const int j, const int k, const int l, int x){
    // ZF_LOGD("xyz: %i, %i, %i, %i, %lf",i,j,k,l,x);
    data->data[i*data->component*data->dim3*data->dim2+j*data->component*data->dim3+k*data->component+l]=x;
}

void DatFile_4D_int_read(DatPtr_4D_int data, const char *file){
    FILE *fp = fopen(file,"r");
    char *line=NULL;
    size_t len=0;
    ssize_t read;
    int temp;
    int x,y,z;
    // First line of the file is for dimensions
    // getline(&line,&len,fp);
    fscanf(fp,"%i %i %i",&x,&y,&z);
    // ZF_LOGD("debug %i %i %i",x,y,z);
    // ZF_LOGD("file: %p, %p, %p, %p, %p",data,&data->data, data->data, &data->data[0], &data->data[1]);
    // data->dim1 = x;
    // data->dim2 = y;
    // data->dim3 = z;
    size_t lineCount=x*y*z;
    for (size_t count = 0; count < lineCount; count++){
        fscanf(fp,"%i %i %i",&x,&y,&z);
        // ZF_LOGD("dat:  %i %i %i",x,y,z);
        for (size_t i = 0; i < data->component; i++)
        {
            fscanf(fp,"%i",&temp);
            // ZF_LOGD("dat:  %i %i %i %i",x,y,z,temp);
            Dat_4D_int_set(data,x-1,y-1,z-1,i,temp);
            // ZF_LOGD("dat:  %i %i %i %i",x,y,z,temp);          
            // ZF_LOGD("afterward: %lf",data->data[count]);
        }
    }
    fclose(fp);
}

void DatFile_4D_int_write(DatPtr_4D_int data, const char *file){
    FILE *fp = fopen(file,"w");
    char *line=NULL;
    size_t len=0;
    ssize_t read;
    // First line of the file is for dimensions
    fprintf(fp,"%li %li %li \n",data->dim1,data->dim2,data->dim3);
    for (size_t i = 0; i < data->dim1; i++){
        for (size_t j = 0; j < data->dim2; j++){
            for (size_t k = 0; k < data->dim3; k++){
                fprintf(fp,"%li %li %li ",i+1,j+1,k+1);
                for (size_t l = 0; l < data->component; l++){
                    fprintf(fp,"%f ",Dat_4D_int_get(data,i,j,k,l));
                }
                fprintf(fp,"\n");
            }
        }
    }
    fclose(fp);
    if(line)free(line);
}