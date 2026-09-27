#include "nmathbasic/nmathbasic.h"

void n_tensor_rank12_print_screen(const char *name, double *input)
{
    ZF_LOGI("---------Begin 3th rank tensor %s-------------", name);
    char temp[50] = {'\0'};
    char temp9[1024] = {'\0'};
    size_t i = 0;
    size_t j = 0;
    size_t k = 0;
    for (i = 0; i < 3; i++)
    {
        temp9[0] = '\0';
        for (j = 0; j < 3; j++)
        {
            for (k = 0; k < 3; k++)
            {
                sprintf(temp, "%zu%zu%zu = %13.6le", i + 1, j + 1, k + 1, input[9 * i + 3 * j + k]);
                n_string_join(temp9, temp9, temp, " ");
            }
            ZF_LOGI("%s", temp9);
        }
    }
    ZF_LOGI("--------- End 3th rank tensor %s -------------", name);
}

void n_tensor_rank12_print_file(const char *name, double *input)
{
    FILE *fp;
    char temp[512] = {'\0'};
    char temp9[1024] = {'\0'};
    fp = fopen(name, "w");
    fprintf(fp, "Index,11,12,13,21,22,23,31,32,33\n");
    size_t i = 0;
    //size_t j = 0;
    size_t k = 0;
    size_t l = 0;
    for (i = 0; i < 3; i++)
    {
            temp9[0] = '\0';
            sprintf(temp9, "%zu", i + 1);
            for (k = 0; k < 3; k++)
            {
                for (l = 0; l < 3; l++)
                {
                    sprintf(temp, ",%13.6le", input[ 9 * i + 3 * k + l]);
                    strcat(temp9, temp);
                }
            }
            fprintf(fp,"%s\n", temp9);
    }
    fclose(fp);
}