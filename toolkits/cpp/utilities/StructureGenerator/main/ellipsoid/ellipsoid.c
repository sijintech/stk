#include <nstructuregenerator/structuregenerator.h>
#include <niobasic/niobasic.h>
#include <zf_log.h>

int main(){
    ZF_LOGD("Hello world for the %s","ellipsoid");
    ControlFilePtr cf = n_ControlFile_init("ellipsoid.xml", NULL);
    int a = n_ControlFile_get_int_by_xpath(cf->doc, "/input/test", "",1);
    ZF_LOGD("The test %i",a);

    NEllipsoidPtr ellipsoid = n_NEllipsoid_init_from_file("ellipsoid.xml","/input/geometry");
    n_NEllipsoid_print(ellipsoid,"");

    short (*dat)[100][100][100];
    n_data_3D_short_init(100, 100, 100, &dat);
    n_data_3D_short_assign(100,100,100, *dat, 0);
    n_generate_NEllipsoid_from_file(100,100,100,*dat,"ellipsoid.xml","/input/geometry");
    n_vtiFile_3D_short_write(100,100,100,*dat,"test_dat.vti");
    ZF_LOGD("A single ellipsoid finished");


    short (*dat1)[100][100][100];
    n_data_3D_short_init(100, 100, 100, &dat1);
    n_data_3D_short_assign(100,100,100, *dat1, 0);
    n_generate_NEllipsoid_random_scale_from_file(100,100,100,*dat1,"ellipsoid.xml","/input/geometry1");
    n_vtiFile_3D_short_write(100,100,100,*dat1,"test_random_scale.vti");
    ZF_LOGD("Random ellipsoid random scale finished");

    short (*dat2)[100][100][100];
    n_data_3D_short_init(100, 100, 100, &dat2);
    n_data_3D_short_assign(100,100,100, *dat2, 0);
    n_generate_NEllipsoid_random_from_file(100,100,100,*dat2,"ellipsoid.xml","/input/geometry2");
    n_vtiFile_3D_short_write(100,100,100,*dat2,"test_random.vti");
    ZF_LOGD("Random ellipsoid fully random finished");

    // short (*dat3)[100][100][100];
    n_data_3D_short_init(100, 100, 100, &dat);
    n_data_3D_short_assign(100,100,100, *dat, 0);
    n_generate_NEllipsoidShell_from_file(100,100,100,*dat,"ellipsoid.xml","/input/geometry3");
    n_vtiFile_3D_short_write(100,100,100,*dat,"test_shell.vti");
    ZF_LOGD("A single ellipsoid shell finished");

}