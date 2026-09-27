#include <nstructuregenerator/structuregenerator.h>
#include <niobasic/niobasic.h>
#include <zf_log.h>

int main(){
    ZF_LOGD("Hello world for the %s","slab");
    ControlFilePtr cf = n_ControlFile_init("slab.xml", NULL);
    int a = n_ControlFile_get_int_by_xpath(cf->doc, "/input/test", "",1);
    ZF_LOGD("The test %i",a);

    NSlabPtr slab = n_NSlab_init_from_file("slab.xml","/input/geometry");
    n_NSlab_print(slab,"");

    short (*dat)[5][1][10];
    n_data_3D_short_init(5, 1, 10, &dat);
    n_data_3D_short_assign(5,1,10, *dat, 0);

    n_generate_NSlab_from_file(5, 1, 10, NPTR2ARR3D(short, *dat,5, 1, 10),"slab.xml","/input/geometry");
    n_vtiFile_3D_short_write(5, 1, 10,*dat,"test_dat.vti");
    ZF_LOGD("A single slab finished");

}