#include <niobasic/figureFile.h>
#include <stdio.h>

// int main ()
// {
//     int height = 361;
//     int width = 867;
//     unsigned char image[height][width][BYTES_PER_PIXEL];
//     char* imageFileName = (char*) "bitmapImage.bmp";

//     int i, j;
//     for (i = 0; i < height; i++) {
//         for (j = 0; j < width; j++) {
//             image[i][j][2] = (unsigned char) ( i * 255 / height );             ///red
//             image[i][j][1] = (unsigned char) ( j * 255 / width );              ///green
//             image[i][j][0] = (unsigned char) ( (i+j) * 255 / (height+width) ); ///blue
//         }
//     }

//     generateBitmapImage((unsigned char*) image, height, width, imageFileName);
//     printf("Image generated!!");
// }


void generateBMP(char* imageFileName, int ncolor, double *colormap , int width, int height, double *image  ){
    unsigned char *image_uchar = malloc(height*width*BYTES_PER_PIXEL*sizeof(unsigned char));
    int *color = malloc(height*width*BYTES_PER_PIXEL*sizeof(int));
    convert_array_double_to_BGR(ncolor, colormap, width, height, image, color);
    convert_array_int_to_uchar(color, image_uchar, height*width*BYTES_PER_PIXEL);
    generateBitmapImage(image_uchar, height, width, imageFileName);
    free(color);
    free(image_uchar);
}

// when doing the conversion, need to switch the array from width*height to height*width
void convert_array_double_to_BGR(int ncolor, double *colormap, int width, int height, double *image,  int *color){

}

void convert_double_to_BGR(int ncolor, double *colormap, double input, int *output){

}

void convert_array_int_to_uchar(int *image_int, unsigned char *image_uchar, int total_size){
    size_t i = 0;
    for (i = 0; i < total_size; i++)
    {
        image_uchar[i] = (unsigned char) image_int[i];
    }
    
}

void generateBitmapImage (unsigned char* image, int height, int width, char* imageFileName)
{
    int widthInBytes = width * BYTES_PER_PIXEL;

    unsigned char padding[3] = {0, 0, 0};
    int paddingSize = (4 - (widthInBytes) % 4) % 4;

    int stride = (widthInBytes) + paddingSize;

    FILE* imageFile = fopen(imageFileName, "wb");

    unsigned char* fileHeader = createBitmapFileHeader(height, stride);
    fwrite(fileHeader, 1, FILE_HEADER_SIZE, imageFile);

    unsigned char* infoHeader = createBitmapInfoHeader(height, width);
    fwrite(infoHeader, 1, INFO_HEADER_SIZE, imageFile);

    int i;
    for (i = 0; i < height; i++) {
        fwrite(image + (i*widthInBytes), BYTES_PER_PIXEL, width, imageFile);
        fwrite(padding, 1, paddingSize, imageFile);
    }

    fclose(imageFile);
}

unsigned char* createBitmapFileHeader (int height, int stride)
{
    int fileSize = FILE_HEADER_SIZE + INFO_HEADER_SIZE + (stride * height);

    static unsigned char fileHeader[] = {
        0,0,     /// signature
        0,0,0,0, /// image file size in bytes
        0,0,0,0, /// reserved
        0,0,0,0, /// start of pixel array
    };

    fileHeader[ 0] = (unsigned char)('B');
    fileHeader[ 1] = (unsigned char)('M');
    fileHeader[ 2] = (unsigned char)(fileSize      );
    fileHeader[ 3] = (unsigned char)(fileSize >>  8);
    fileHeader[ 4] = (unsigned char)(fileSize >> 16);
    fileHeader[ 5] = (unsigned char)(fileSize >> 24);
    fileHeader[10] = (unsigned char)(FILE_HEADER_SIZE + INFO_HEADER_SIZE);

    return fileHeader;
}

unsigned char* createBitmapInfoHeader (int height, int width)
{
    static unsigned char infoHeader[] = {
        0,0,0,0, /// header size
        0,0,0,0, /// image width
        0,0,0,0, /// image height
        0,0,     /// number of color planes
        0,0,     /// bits per pixel
        0,0,0,0, /// compression
        0,0,0,0, /// image size
        0,0,0,0, /// horizontal resolution
        0,0,0,0, /// vertical resolution
        0,0,0,0, /// colors in color table
        0,0,0,0, /// important color count
    };

    infoHeader[ 0] = (unsigned char)(INFO_HEADER_SIZE);
    infoHeader[ 4] = (unsigned char)(width      );
    infoHeader[ 5] = (unsigned char)(width >>  8);
    infoHeader[ 6] = (unsigned char)(width >> 16);
    infoHeader[ 7] = (unsigned char)(width >> 24);
    infoHeader[ 8] = (unsigned char)(height      );
    infoHeader[ 9] = (unsigned char)(height >>  8);
    infoHeader[10] = (unsigned char)(height >> 16);
    infoHeader[11] = (unsigned char)(height >> 24);
    infoHeader[12] = (unsigned char)(1);
    infoHeader[14] = (unsigned char)(BYTES_PER_PIXEL*8);

    return infoHeader;
}