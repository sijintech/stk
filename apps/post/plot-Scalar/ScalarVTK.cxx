/*=========================================================================

Program:   Visualization Toolkit
Module:    FixedPointVolumeRayCastMapperCT.cxx

Copyright (c) Ken Martin, Will Schroeder, Bill Lorensen
All rights reserved.
See Copyright.txt or http://www.kitware.com/Copyright.htm for details.

This software is distributed WITHOUT ANY WARRANTY; without even
the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
PURPOSE.  See the above copyright notice for more information.

=========================================================================*/
#include <vtkAutoInit.h> 
VTK_MODULE_INIT(vtkRenderingOpenGL); 
VTK_MODULE_INIT(vtkInteractionStyle); 
VTK_MODULE_INIT(vtkRenderingFreeType); 
VTK_MODULE_INIT(vtkRenderingVolumeOpenGL);

// VTK includes
#include "vtkCamera.h"
#include "vtkCommand.h"
#include "vtkColorTransferFunction.h"
#include "vtkImageResample.h"
#include "vtkMetaImageReader.h"
#include "vtkPiecewiseFunction.h"
#include "vtkPlanes.h"
#include "vtkProperty.h"
#include "vtkRenderer.h"
#include "vtkRenderWindow.h"
#include "vtkRenderWindowInteractor.h"
#include "vtkVolume.h"
#include "vtkVolumeProperty.h"
//#include "vtkFixedPointVolumeRayCastMapper.h"
//#include "vtkGPUVolumeRayCastMapper.h"
#include "vtkSmartVolumeMapper.h"
#include "vtkXMLImageDataReader.h"
#include "vtkImageData.h"
#include "vtkCallbackCommand.h"
#include "vtkPointData.h"
#include "vtkInteractorStyleTrackballCamera.h"

#include "vtkScalarBarWidget.h"
#include "vtkScalarBarActor.h"
#include "vtkCamera.h"
#include "vtkWindowToImageFilter.h"
#include "vtkPNGWriter.h"

#include <FreeFormatOneLine.h>
#include <FreeFormatParser.h>
#include <Dataset.h>
#include <sstream>
#include <iostream>
#include <iomanip>
#include <ScreenPrint.h>
#include <CustomInteractorStyle.h>
#define VTI_FILETYPE 1
#define DAT_FILETYPE 2

#define VTK_CREATE(type, name) \
    vtkSmartPointer<type> name = vtkSmartPointer<type>::New()

using namespace std;


string fileNameGlob;
void arraySwitchCallbackFunction(vtkObject* caller, long unsigned int eventId, void* clientData, void* callData){
    /* VTK_CREATE(vtkSmartVolumeMapper,mapper); */
    vtkRenderWindowInteractor *iren = static_cast<vtkRenderWindowInteractor*>(caller);

    vtkSmartVolumeMapper* map=reinterpret_cast<vtkSmartVolumeMapper*>(clientData);

    int number=(int)*iren->GetKeySym()-49;
    int colNum=map->GetInput()->GetPointData()->GetNumberOfArrays();
    cout << "PressedSwitched:" << number<<" "<<colNum<<endl;
    if (number<=colNum-1 && number >=0) {
        map->SelectScalarArray(number);
        map->Update();
    }

}

string autoFileNamer(string fileName){
    string name,extension,outName,indexString;
    int index;
    stringstream ss;
    index = 0;
    ss.clear();
    ss.str("");
    ss << setw(3)<< setfill('0') << index ;
    indexString = ss.str();
    name = fileName.substr(0,fileName.find_last_of("."));
    extension = fileName.substr(fileName.find_last_of(".")+1);

    outName = name + "." + indexString + "." + extension;
    /* cout << "auto namer" << outName <<endl; */
    while (ifstream(outName)){
        index = index + 1;
        ss.clear();
        ss.str("");
        ss << setw(3) << index ;
        indexString = ss.str();
        outName = name + "." + indexString + "." + extension;
        /* cout << "autonamer" << outName << endl; */
    }
    return outName;
}

void imageSaveCallbackFunction(vtkObject* caller, long unsigned int eventId, void* clientData, void* callData){
    /* VTK_CREATE(vtkSmartVolumeMapper,mapper); */
    vtkRenderWindowInteractor *iren = static_cast<vtkRenderWindowInteractor*>(caller);

    /* string fileName=reinterpret_cast<string>(clientData); */
    vtkRenderWindow* renWin=iren->GetRenderWindow();

    VTK_CREATE(vtkWindowToImageFilter,windowToImageFilter);
    VTK_CREATE(vtkPNGWriter,writer);

    string imageName;
    int index;



    int number=(int)*iren->GetKeySym();
    if (number==115) {
        imageName = autoFileNamer(fileNameGlob);
        cout << "PressedImage:" << imageName << " " <<fileNameGlob << " " << number<<endl;
        renWin->SetOffScreenRendering(1);
        renWin->Render();
        windowToImageFilter->SetInput(renWin);
        windowToImageFilter->Update();
        writer->SetFileName(imageName.c_str());
        writer->SetInputConnection(windowToImageFilter->GetOutputPort());
        writer->Write();
        renWin->SetOffScreenRendering(0);
    }


}

int main(int argc, char *argv[])
{
    // Parse the parameters

    char *dirname = NULL;
    double opacityWindow = 4096;
    double opacityLevel = 2048;
    int blendType = 0;
    int clip = 0;
    vector<string> fileName;
    vector<string> vtiFileName;
    vector<string> imageName;

    bool fileFormatSTD=true;
    bool viewWindow = true;
    bool outputScalarAnalysis = false;
    double R,G,B,Alpha,Value;
    string shortFileName="",midFileName="",extension="";

    int start=0,delta=0,end=0,count=1;
    double focalX,focalY,focalZ;
    double positionX,positionY,positionZ;
    double upX,upY,upZ;
    double scalarMin,scalarMax;
    double scalarRange[2];
    string cameraName;
    int datDim[4];
    int printWidth=80;

    double reductionFactor = 1.0;
    double frameRate = 10.0;
    int fileType=0;
    char **firstLevel[300],**secondLevel[300];

    bool independentComponents=true;
    vector<vector<double> > lookUpTable;
    vector<double> colorHold;
    bool controlFileExist=false;
    bool showLegend=false;
    int colorCount=0;
    string choiceColor;

    ostringstream stringstream;

    FreeFormatParser structRead;
    ScreenPrint print;
    std::string outMessage;

    colorHold.resize(5);

    /* cout << "good1" << endl; */
    structRead.setFilename("visualScalar.in");
    /* cout << "good1" << endl; */
    controlFileExist=structRead.parse();
    /* cout << "good1" << endl; */

    print.setWidth(120);
    print.setColumnWidth(40);
    print.setNumberWidth(15);

    if (controlFileExist) {
        print.printCenter("Start to read the visual.in file",'-');
        if (structRead.firstKeyExist("LSTDFORMAT")) {
            istringstream(structRead.getFirstLevel("LSTDFORMAT")[0]) >> boolalpha >>  fileFormatSTD;
            print.printVariable("Choose to use the standard dat format",fileFormatSTD);
        }else{
            print.printVariable("LSTDFORMAT is not set, use default",fileFormatSTD);
        }


    }else if(argc>1){
        print.printLeft("Get parameter from command line",' ');
    }else{
        print.printError("Either the visual.in file need to be given or a arguement is needed by the program");
        exit(-1);
    }




    if (argc==1) {
        viewWindow=false;
        outputScalarAnalysis=false;

        if (structRead.firstKeyExist("FILENAME")) {
            shortFileName = structRead.getFirstLevel("FILENAME")[0]; 
            print.printVariable("The common file name",shortFileName) ;
        }else{
            print.printError("The FILENAME is not set yet");
            exit(-1);
        }


        if (structRead.firstKeyExist("EXTENSION")) {
            extension = structRead.getFirstLevel("EXTENSION")[0];
            print.printVariable("The data extension",extension);
        }else{
            extension = "dat";
            print.printVariable("No extension is set, use default",extension);
        }


        if (fileFormatSTD) {
            if (structRead.firstKeyExist("START")) {
                istringstream(structRead.getFirstLevel("start")[0]) >> start ;
                print.printVariable("The starting time step",start);
            }else{
                print.printVariable("No initial time step set, use the default value ",start);
            }
            if (structRead.firstKeyExist("END")) {
                istringstream(structRead.getFirstLevel("end")[0]) >> end;
                print.printVariable("The end time step is ",end); 
            }else{
                print.printVariable("No end time step set, use the default value ", end);
            }
            if (structRead.firstKeyExist("DELTA")) {
                istringstream(structRead.getFirstLevel("delta")[0]) >> delta;
                print.printVariable("The delta time step is",delta); 
            }else{
                delta = end - start;
                print.printVariable("No delta time step is set, use the default value ",delta); 
            }
            if (delta!=0) {
                count = (end-start)/delta + 1;
            }else{
                count = 1;
            }
            for (int i = 0; i < count; i++) {

                stringstream.clear();
                stringstream.str("");
                stringstream << setw(8) << setfill('0') << i*delta+start ;

                midFileName = stringstream.str();
                fileName.push_back(shortFileName + "." + midFileName + "." + extension); 
            }

        }else{
            count=1;
            fileName.push_back(shortFileName + "." + extension);
            print.printVariable("The fileName is ", fileName[0]);
        }

        print.printVariable("Numbers of file to be visualized ", count);


    }else{
        viewWindow=true;
        fileName.push_back(argv[1]);
        outputScalarAnalysis=true;
        extension=fileName[0].substr(fileName[0].find_last_of(".")+1);
        outMessage= "Visualize the file "+fileName[0];
        print.printCenter(outMessage,'-');
        print.printVariable("File extension",extension);
    }

    if (structRead.firstKeyExist("SHOWLEGEND")) {
        istringstream(structRead.getFirstLevel("SHOWLEGEND")[0]) >> boolalpha >>  showLegend;
        print.printVariable("Choose to show the scalar legend",showLegend);
    }else{
        print.printVariable("Default option for scalar legend bar",showLegend);
    }




    print.printLeft("Finished reading the visual.in file.",'-');


    print.printLeft("Initialize vtk.",'-');


    if (count > 1) {
        // a place holder for the future scalar data analysis
    }

    for (int i = 0; i < count; i++) {

        print.printVariable("Start to read data file", fileName[i]);
        if( extension == "vti" )
        {
            vtiFileName.push_back(fileName[i]);
            imageName.push_back(fileName[i].substr(0,fileName[i].find_last_of("."))+".png");
        }
        else if ( extension == "dat" )
        {
            Dataset dat;
            dat.setDatFileName(fileName[i]);
            dat.readDatFile();
            dat.getDimension(datDim);

            dat.outputVTIFile();

            print.printLeft("Dat file is converted to vti file for visualization",'-');
            vtiFileName.push_back(dat.getVTIFileName());
            imageName.push_back(dat.getLongFileName()+".png");
        }
        else
        {
            print.printError( "Error! Not VTI or DAT!");
            exit(EXIT_FAILURE);
        }
    }


    focalX = datDim[0]/2;
    focalY = datDim[1]/2;
    focalZ = datDim[2]/2;
    positionX = datDim[0]*2;
    positionY = datDim[1]*2;
    positionZ = datDim[2]*2;
    upX = -1;
    upY = -1;
    upZ = 2;

    /* The LOOKUPTABLE, and some camera related values are 
     * set after reading the file because the they need some 
     * information of the data*/
    if (structRead.firstKeyExist("LOOKUPTABLE")) {
        choiceColor = structRead.getFirstLevel("LOOKUPTABLE")[0];
        print.printVariable("Use the lookuptable ", choiceColor); 
        if (structRead.secondKeyExist(choiceColor,"POINTADD")) {
            colorCount = structRead.getSecondLevel(choiceColor,"POINTADD").size();
            print.printVariable("Number of colors in table ", colorCount); 
            for (int i = 0; i < colorCount; i++) {
                istringstream(structRead.getSecondLevel(choiceColor,"POINTADD")[i]) >> Value >>R >> G >> B >> Alpha; 
                colorHold[0] = Value;
                colorHold[1] = R;
                colorHold[2] = G;
                colorHold[3] = B;
                colorHold[4] = Alpha;
                lookUpTable.push_back(colorHold);
                print.printVariable("Add color pivot ", Value, R ,G,B, Alpha);

            }
        }
    }else{
        print.printLeft("No lookuptable specified, use the default one",' ');
    }

    if (structRead.firstKeyExist("CAMERA")) {
        cameraName = structRead.getFirstLevel("CAMERA")[0];
        print.printVariable( "Choose to use the camera ", cameraName);
        if (structRead.secondKeyExist(cameraName,"FOCAL")) {
            istringstream(structRead.getSecondLevel(cameraName,"FOCAL")[0]) >> focalX >> focalY >> focalZ;
            print.printVariable("Camera focal point set to", focalX, focalY, focalZ);
        }else{
            print.printVariable("Use default value for camera focal point",focalX, focalY,focalZ);
        }

        if (structRead.secondKeyExist(cameraName,"POSITION")) {
            istringstream(structRead.getSecondLevel(cameraName,"POSITION")[0]) >> positionX >> positionY >> positionZ;
            print.printVariable("Camera position set to",positionX,positionY,positionZ);
        }else{
            print.printVariable("Use default value for camera position",positionX,positionY,positionZ);
        }

        if (structRead.secondKeyExist(cameraName,"UP")) {
            istringstream(structRead.getSecondLevel(cameraName,"UP")[0]) >> upX >> upY >> upZ;
            print.printVariable("Camera up direction set to",upX,upY,upZ);
        }else{
            print.printVariable("Use default value for camera up direction",upX,upY,upZ);
        }


    }else{
        print.printCenter("No camera specified, use the default one",' ');
    }

    for (int m = 0; m < count; m++) {

        VTK_CREATE(vtkRenderer,renderer);
        VTK_CREATE(vtkRenderWindow,renWin);

        // Connect it all. Note that funny arithematic on the
        // SetDesiredUpdateRate - the vtkRenderWindow divides it
        // allocated time across all renderers, and the renderer
        // divides it time across all props. If clip is
        // true then there are two props
        VTK_CREATE(vtkRenderWindowInteractor,iren);
        /* VTK_CREATE(vtkInteractorStyleTrackballCamera,style); */
        VTK_CREATE(CustomInteractorStyle,style);
        // Read the data
        VTK_CREATE(vtkXMLImageDataReader,reader);
        VTK_CREATE(vtkImageData,input);

        VTK_CREATE(vtkVolume,volume);
        VTK_CREATE(vtkSmartVolumeMapper,mapper);
        VTK_CREATE(vtkColorTransferFunction,color);
        VTK_CREATE(vtkPiecewiseFunction,compositeOpacity);
        VTK_CREATE(vtkVolumeProperty,property);

        VTK_CREATE(vtkScalarBarWidget,scalarLegendWidget);
        VTK_CREATE(vtkScalarBarActor,scaleBarActor);
        VTK_CREATE(vtkCamera,camera);
        VTK_CREATE(vtkWindowToImageFilter,windowToImageFilter);
        VTK_CREATE(vtkPNGWriter,writer);

        VTK_CREATE(vtkCallbackCommand,arraySwitchCallback);
        VTK_CREATE(vtkCallbackCommand,imageSaveCallback);
        /* fileNameGlob=imageName[m]; */
        style->setDatFile(imageName[m]);
        style->setVolumeOn();
        /* imageSaveCallback->SetClientData(imageName[m]); */






        print.printVariable("Visualizing file",vtiFileName[m]);
        reader -> SetFileName(vtiFileName[m].c_str());
        reader->Update();

        /* input->ShallowCopy(reader->GetOutput()); */

        // Create our volume and mapper
        /* cout << reader->GetPointArrayStatus(reader->GetPointArrayName(1)) << endl;; */
        mapper->SetInputData( reader->GetOutput() );
        mapper->SelectScalarArray(0);
        mapper->SetBlendModeToComposite();


        // Set the sample distance on the ray to be 1/2 the average spacing



        // Create our transfer function
        /* vtkColorTransferFunction *colorFun = vtkColorTransferFunction::New(); */
        /* vtkPiecewiseFunction *opacityFun = vtkPiecewiseFunction::New(); */

        // Create the property and attach the transfer functions
        /* vtkVolumeProperty *property = vtkVolumeProperty::New(); */
        /* property->ShadeOff(); */

        print.printLeft("Setting up color and opacity for the data",' ');
        if (colorCount>0) {
            print.printLeft("Use value specified in visual.in",' ');
        }else{
            print.printLeft("Use default color value",' ');
            /* reader->GetOutput()->GetPointData()->Print(cout); */


            reader->GetOutput()->GetPointData()->GetArray(0)->GetRange(scalarRange);
            scalarMin=scalarRange[0];
            scalarMax=scalarRange[1];

            int colNum=mapper->GetInput()->GetPointData()->GetNumberOfArrays();
            for (int i = 0; i < colNum; i++) {

                reader->GetOutput()->GetPointData()->GetArray(i)->GetRange(scalarRange);
                reader->Update();
                scalarMin=min(scalarMin,scalarRange[0]);
                scalarMax=max(scalarMax,scalarRange[1]);
            }
            print.printVariable("The min value for lookuptable", scalarMin);
            print.printVariable("The max value for lookuptable", scalarMax);
            colorHold[0] = scalarMin;
            colorHold[1] = 0.0;
            colorHold[2] = 0.0;
            colorHold[3] = 1.0;
            colorHold[4] = 1.0;
            lookUpTable.push_back(colorHold);
            print.printVariable("Add color pivot ", colorHold[0],colorHold[1],colorHold[2],colorHold[3],colorHold[4]);
            colorHold[0] = (scalarMin+scalarMax)/2.0;
            colorHold[1] = 0.0;
            colorHold[2] = 1.0;
            colorHold[3] = 0.0;
            colorHold[4] = 1.0;
            lookUpTable.push_back(colorHold);
            print.printVariable("Add color pivot ", colorHold[0],colorHold[1],colorHold[2],colorHold[3],colorHold[4]);
            colorHold[0] = scalarMax;
            colorHold[1] = 1.0;
            colorHold[2] = 0.0;
            colorHold[3] = 0.0;
            colorHold[4] = 1.0;
            lookUpTable.push_back(colorHold);
            print.printVariable("Add color pivot ", colorHold[0],colorHold[1],colorHold[2],colorHold[3],colorHold[4]);
            colorCount=3;

        }

        for (int i = 0; i < lookUpTable.size(); i++) {
            cout << "i" << i << " " <<lookUpTable[i][0] <<lookUpTable[i][1] <<lookUpTable[i][2] <<lookUpTable[i][3] <<lookUpTable[i][4] << endl;
            compositeOpacity->AddPoint(lookUpTable[i][0],lookUpTable[i][4]);
            color->AddRGBPoint(lookUpTable[i][0],lookUpTable[i][1],lookUpTable[i][2],lookUpTable[i][3]);
        }
        property->SetInterpolationType(VTK_LINEAR_INTERPOLATION);
        property->SetScalarOpacity(compositeOpacity); // composite first.
        property->SetColor(color);
        volume->SetProperty( property );


        volume->SetMapper( mapper );
        mapper->SetScalarModeToUsePointFieldData();
        mapper->SelectScalarArray(0);
        mapper->Update();
        volume->Update();
        renderer->AddVolume( volume );

        mapper->SetRequestedRenderModeToRayCast();

        renWin->AddRenderer(renderer);
        renderer->SetBackground(1,1,1);




        camera->SetFocalPoint(focalX,focalY,focalZ);
        camera->SetPosition(positionX,positionY,positionZ);
        camera->SetViewUp(upX,upY,upZ);
        renderer->SetActiveCamera(camera);

        scaleBarActor->SetLookupTable(color);
        scaleBarActor->SetNumberOfLabels(4);
        /* scalarBarActor->SetTitle("Title"); */

        if (viewWindow) {
            print.printVariable("Opening render window for",fileName[m]);



            /* arraySwitchCallback->SetCallback(arraySwitchCallbackFunction); */
            /* arraySwitchCallback->SetClientData(mapper); */
            /* imageSaveCallback->SetCallback(imageSaveCallbackFunction); */

            renWin->SetSize(600,600);
            /* iren->Initialize(); */
            /* iren->AddObserver(vtkCommand::KeyPressEvent,arraySwitchCallback); */
            /* iren->AddObserver(vtkCommand::KeyPressEvent,imageSaveCallback); */
            iren->SetRenderWindow(renWin);

            scalarLegendWidget->SetInteractor(iren);
            scalarLegendWidget->SetScalarBarActor(scaleBarActor);
            scalarLegendWidget->ResizableOn();
            if (showLegend) {
                scalarLegendWidget->On();
                scaleBarActor->SetVisibility(true);
            }else{
                scalarLegendWidget->Off();
                scaleBarActor->SetVisibility(false);
            }



            renWin->Render();
            iren->SetDesiredUpdateRate(20);
            iren->SetInteractorStyle(style);
            iren->Start();
        }else{
            print.printVariable("Rendering off screen", imageName[m]);
            renWin->SetOffScreenRendering(1);
            renderer->AddActor2D(scaleBarActor);
            renWin->Render();
            windowToImageFilter->SetInput(renWin);
            windowToImageFilter->Update();
            writer->SetFileName(imageName[m].c_str());
            writer->SetInputConnection(windowToImageFilter->GetOutputPort());
            writer->Write();

        }

        //    color->Delete();
        //    property->Delete();
        //
        //    volume->Delete();
        //    mapper->Delete();
        //    reader->Delete();
        //    renderer->Delete();
        //    renWin->Delete();
        //    iren->Delete();
        //    style->Delete();
        //    color->Delete();
        //    compositeOpacity->Delete();


    }
    return 0;
}
