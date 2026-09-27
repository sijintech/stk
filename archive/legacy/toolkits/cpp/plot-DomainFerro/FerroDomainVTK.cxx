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
// VTK includes
#include "vtkBoxWidget.h"
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
#include "vtkXMLImageDataReader.h"
#include "vtkImageData.h"
#include "vtkDataSetMapper.h"
#include "vtkThreshold.h"
#include "vtkDataSetSurfaceFilter.h"
#include "vtkSmoothPolyDataFilter.h"
#include "vtkPolyDataNormals.h"
#include "vtkCallbackCommand.h"
#include "vtkPointData.h"
#include "vtkInteractorStyleTrackballCamera.h"
#include "vtkWindowToImageFilter.h"
#include "vtkPNGWriter.h"
#include "vtkUnstructuredGrid.h"

#include <FreeFormatOneLine.h>
#include <FreeFormatParser.h>
#include <VectorDomainDataset.h>
#include <FerroDomain.h>
#include <Data.h>
#include <sstream>
#include <iostream>
#include <ScreenPrint.h>
#include <CustomInteractorStyle.h>

#define VTI_FILETYPE 1
#define DAT_FILETYPE 2

#define VTK_CREATE(type, name) \
    vtkSmartPointer<type> name = vtkSmartPointer<type>::New()

using namespace std;

//void KeypressCallbackFunction(vtkObject* caller, long unsigned int eventId, void* clientData, void* callData){
//    /* VTK_CREATE(vtkSmartVolumeMapper,mapper); */
//    vtkRenderWindowInteractor *iren = static_cast<vtkRenderWindowInteractor*>(caller);
//
//    vtkSmartVolumeMapper* map=reinterpret_cast<vtkSmartVolumeMapper*>(clientData);
//
//    int number=(int)*iren->GetKeySym()-49;
//    int colNum=map->GetInput()->GetPointData()->GetNumberOfArrays();
//    cout << "Pressed:" << number<<colNum<<endl;
//    if (number<=colNum-1 && number >=0) {
//    map->SelectScalarArray(number);
//    map->Update();
//    }
//
//}

int main(int argc, char *argv[])
{
    // Parse the parameters

    double opacityWindow = 4096;
    double opacityLevel = 2048;
    int blendType = 0;
    int clip = 0;
    double reductionFactor = 1.0;
    double frameRate = 10.0;
    vector<string> fileName;
    vector<string> vtiFileName;
    vector<string> imageName;
    char **firstLevel[300],**secondLevel[300];

    bool independentComponents=true;
    bool fileFormatSTD=true;
    bool viewWindow = true;
    bool outputDomainAnalysis = false;
    double R,G,B,Alpha;
    int Value;
    string shortFileName="",midFileName="",extension="";
    string choiceColor;
    int start=0,delta=0,end=0,count=1;
    double domainValue,domainAngle;
    double focalX,focalY,focalZ;
    double positionX,positionY,positionZ;
    double upX,upY,upZ;
    double clipNear,clipFar;
    ostringstream stringstream("");
    Data domainInfo;
    string cameraName;
    int datDim[4];
    int printWidth=80;
    double ** lookUpTable;
    bool * domainVisibility; 
    int domainTypeCount=0;
    int colorCount=0;
    bool controlFileExist=false;
    bool visibleAll=true;
    int number;
    int windowX=600,windowY=600;

    /* First setup to read the struct.in file 
     * The LSTDFORMAT, FILENAME, EXTENSION, START, DELTA, END
     * DOMAINVALUE, DOMAINANGLE tags can be read first
     *
     * */ 

    ScreenPrint print;
    print.setWidth(120);
    print.setColumnWidth(60);
    print.setNumberWidth(11);

    FreeFormatParser structRead;
    structRead.setFilename("visualPolar.in");
    controlFileExist=structRead.parse();

    if (controlFileExist) {
        /* cout << "Start to read the visual.in file" << endl; */
        print.printCenter("Start to read the visualPolar.in file",'-');
    }else if(argc>1){
        /* cout << "Get parameter from command line" << endl; */
        print.printLeft("Get file name from the command line",' ');
    }else{
        /* cout << "Either the visual.in file need to be given or a arguement is needed by the program" << endl; */
        print.printLeft("Either the visual.in file need to be given or a arguement is needed by the program",' ' );
        exit(-1);
    }


    if (structRead.firstKeyExist("LSTDFORMAT")) {
        istringstream(structRead.getFirstLevel("LSTDFORMAT")[0]) >> boolalpha >>  fileFormatSTD;
        /* cout << setw(printWidth) << right << "Choose to use the standard dat format " << boolalpha << fileFormatSTD << endl; */
        print.printVariable("Choose to use the standard dat format",fileFormatSTD);
    }else{
        /* cout << setw(printWidth) << right << "No value of LSTDFORMAT is set, use the default value of " << fileFormatSTD << endl; */
        print.printVariable("No value of LSTDFORMAT is set, use the default value of ",fileFormatSTD);
    }

    if (structRead.firstKeyExist("WINSIZE")) {
        istringstream(structRead.getFirstLevel("WINSIZE")[0]) >> windowX >>  windowY;
        print.printVariable("The render widnows size is ",windowX,windowY);
        /* cout << setw(printWidth) << right << "The render window size is  " << windowX << " "<<windowY << endl; */
    }else{
        print.printVariable("No render window size is set, use the default value of ",windowX,windowY);
        /* cout << setw(printWidth) << right << "No render window size is set, use the default value of " << windowX << " " << windowY << endl; */
    }





    /* cout << argc << "argc" << endl; */
    /* If no filename is passed using arguement, 
     * then read FILENAME, EXTENSION, START, DELTA, END
     * from the struct.in file*/

    if (argc==1) {
        viewWindow=false;
        outputDomainAnalysis=false;

        if (structRead.firstKeyExist("FILENAME")) {
            shortFileName = structRead.getFirstLevel("FILENAME")[0]; 
            /* cout << setw(printWidth) << right << "The common file name is " << shortFileName << endl; */
            print.printVariable("The common file name is",shortFileName);
        }else{
            print.printError("The filename is not set yet");
            /* cout << "!!!!!!!!!!!Error!!!!!!!!!!!" << endl; */
            /* cout << "The FILENAME is not set yet" << endl; */
            /* cout << "!!!!!!!!!!!Error!!!!!!!!!!!" << endl; */
            exit(-1);
        }


        if (structRead.firstKeyExist("EXTENSION")) {
            extension = structRead.getFirstLevel("EXTENSION")[0];
            /* cout << setw(printWidth) << right << "The data extension is " << extension << endl; */
            print.printVariable("The data extension is ",extension);
        }else{
            extension = "dat";
            print.printVariable("No extension is specified, use the default one",extension);
            /* cout << setw(printWidth) << right << "No extension is specified, use the default one " << extension << endl; */
        }


        if (fileFormatSTD) {
            if (structRead.firstKeyExist("START")) {
                istringstream(structRead.getFirstLevel("start")[0]) >> start ;
                print.printVariable("The start time step is",start);
                /* cout << setw(printWidth) << right << "The start time step is " << start << endl; */ 
            }else{
                print.printVariable("No initial time step set, use the dedault value",start);
                /* cout << setw(printWidth) << right << "No initial time step set, use the default value " << start << endl; */
            }
            if (structRead.firstKeyExist("END")) {
                istringstream(structRead.getFirstLevel("end")[0]) >> end;
                print.printVariable("The end time step is",end);
                /* cout << setw(printWidth) << right << "The end time step is " << end << endl; */ 
            }else{
                print.printVariable("No end time step set, use the default value",end);
                /* cout << setw(printWidth) << right << "No end time step set, use the default value " << end << endl; */
            }
            if (structRead.firstKeyExist("DELTA")) {
                istringstream(structRead.getFirstLevel("delta")[0]) >> delta;
                print.printVariable("The delta time step is",delta);
                /* cout << setw(printWidth) << right << "The delta time step is " << delta << endl; */ 
            }else{
                delta = end - start;
                print.printVariable("No delta time step is set, use the default value",delta);
                /* cout << setw(printWidth) << right << "No delta time step is set, use the default value " << delta << endl; */ 
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
            print.printVariable("The filename is",fileName[0]);
            /* cout << setw(printWidth) << right << "The fileName is " << fileName[0] << endl; */
        }

        print.printVariable("Number of file to be visualized",count);
        /* cout << setw(printWidth) << right << "Numbers of file to be visualized " << count << endl; */


    }else{
        viewWindow=true;
        fileName.push_back(argv[1]);
        outputDomainAnalysis=true;
        extension=fileName[0].substr(fileName[0].find_last_of(".")+1);
        print.printVariable("Visualize the file",fileName[0]);
        print.printVariable("File extension is",extension);
        /* cout << setw(printWidth) << "Visualize the file " << fileName[0] << endl; */
        /* cout << setw(printWidth) << "File extension is " << extension << endl; */
    }

    if (structRead.firstKeyExist("DOMAINVALUE")) {
        istringstream(structRead.getFirstLevel("domainValue")[0]) >> domainValue;
        print.printVariable("The ferroelectric domain criteria for value is",domainValue);
        /* cout << setw(printWidth) << right << "The ferroelectric domain criteria of value is " << domainValue << endl; */
    }else{
        domainValue = 0.1 ;
        print.printVariable("No ferroelectric domain criteria for value is set, use default value",domainValue);
        /* cout << setw(printWidth) << right << "No ferroelectric domain criteria of value is set, use the default value " << domainValue << endl; */
    }

    if (structRead.firstKeyExist("DOMAINANGLE")) {
        istringstream(structRead.getFirstLevel("domainAngle")[0]) >> domainAngle;
        print.printVariable("The ferroelectric domain criteria for angle is",domainAngle);
        /* cout << setw(printWidth) << right << "The ferroelectric domain criteria of angle is " << domainAngle << endl; */
    }else{
        domainAngle = 180 ;
        print.printVariable("No ferroelectric domain criteria for angle is set, use default value",domainAngle);
        /* cout << setw(printWidth) << right << "No ferroelectric domain criteria of angle is set, use the default value " << domainAngle << endl; */
    }

    if (structRead.firstKeyExist("VISIBLEALL")) {
        istringstream(structRead.getFirstLevel("VISIBLEALL")[0])>>boolalpha >> visibleAll;
        print.printVariable("All domains are visible",visibleAll);
        /* cout << setw(printWidth) << right << "All domains are visible " << boolalpha << visibleAll << endl ; */
    }else{
        visibleAll=true;
        print.printVariable("VISIBLEALL not set, use default value",visibleAll);
        /* cout << setw(printWidth) << right << "Use default value, All domains are visible " << boolalpha << visibleAll << endl ; */
    }



    /* cout << "Finished reading the visual.in file" << endl; */
    print.printCenter("Finished reading the visualPolar.in file",'-');


    FerroDomain domain;
    domain.setStandardValue(domainValue);
    domain.setStandardAngle(domainAngle);
    domain.printDomainInfo();
    domainTypeCount = domain.getDomainTypeCount();

    lookUpTable = new double*[domainTypeCount];
    domainVisibility = new bool[domainTypeCount];
    for (int i = 0; i < domainTypeCount; i++) {
        lookUpTable[i] = new double [4]();
        lookUpTable[i][0] = domain.getDomainR(i);
        lookUpTable[i][1] = domain.getDomainG(i);
        lookUpTable[i][2] = domain.getDomainB(i);
        lookUpTable[i][3] = 1;
        domainVisibility[i] = visibleAll;
    }


    /* cout << "Initialize vtk" << endl; */
    print.printCenter("Initializing vtk",'-');

    // Create the renderer, render window and interactor
    /* vtkRenderer *renderer = vtkRenderer::New(); */

    /* If there are more than one file to visualize
     * then, instead of output the domain analytics data for each file
     * we output them into one single file call Domain_Analytics.txt*/
    if ( count > 1) {
        vector<string> header(domain.getDomainTypeCount()+1);
        header[0]="Index";
        for (int i = 0; i < domain.getDomainTypeCount(); i++) {
            header[i+1]=domain.getDomainTypeLabel(i); 
        }
        domainInfo.setFileName("Domain_Analytics.txt");
        domainInfo.initializeFile(header); 
    }

    for (int i = 0; i < count; i++) {

        /* cout <<setw(printWidth) << right << "Start to read data file " << fileName[i] <<endl; */
        print.printVariable("Start to read data file",fileName[i]);
        if( extension == "vti" )
        {
            vtiFileName.push_back(fileName[i]);
            imageName.push_back(fileName[i].substr(0,fileName[i].find_last_of("."))+".png");
        }
        else if ( extension == "dat" || extension=="test" )
        {
            /* std::cout << fileName[0] << " "<<extension <<endl; */
        if (extension=="test") {
            domain.printTestDat();
        }

            VectorDomainDataset dat;
            dat.setDatFileName(fileName[i]);
            dat.readDatFile();
            dat.getDimension(datDim);
            dat.setOutputDomainAnalysis(outputDomainAnalysis);

            if (datDim[3]==3) {
                dat.outputVTIFile(domain,1);
            } else {
                dat.outputVTIFile(domain,2); 
            }

            if (count >1) {
                vector<double> value(domain.getDomainTypeCount());
                for (int j = 0; j < domain.getDomainTypeCount(); j++) {
                    value[j]=dat.getDomainPercent(j);
                }
                domainInfo.outputWithIndex(i*delta+start,value);
            }


            vtiFileName.push_back(dat.getVTIFileName());
            imageName.push_back(dat.getLongFileName()+".png");
        }else
        {
            /* cout << "Error! Not VTI or DAT!" << endl; */
            print.printError("Not VTI nor DAT");
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
    clipNear=0;
    clipFar=1000;

    /* The LOOKUPTABLE, and some camera related values are 
     * set after reading the file because the they need some 
     * information of the data*/
    if (structRead.firstKeyExist("LOOKUPTABLE")) {
        choiceColor = structRead.getFirstLevel("lookuptable")[0];
        /* cout << setw(printWidth) << right << "Use the lookuptable " << choiceColor << endl; */ 
        print.printVariable("Use the lookuptable",choiceColor);
        if (structRead.secondKeyExist(choiceColor,"POINTADD")) {
            colorCount = structRead.getSecondLevel(choiceColor,"POINTADD").size();
            for (int i = 0; i < colorCount; i++) {
                istringstream(structRead.getSecondLevel(choiceColor,"POINTADD")[i]) >> Value >>R >> G >> B >> Alpha; 
                lookUpTable[Value][0] = R;
                lookUpTable[Value][1] = G;
                lookUpTable[Value][2] = B;
                lookUpTable[Value][3] = Alpha;
                /* cout << setw(printWidth) << right << "Add color pivot " << Value << " " << R << " " << G << " " << " " << B << " " << Alpha << endl; */
                print.printVariable("Add color pivot",Value,R,G,B,Alpha);

            }
        }
    }else{
        print.printCenter("No lookuptable specified, use the default one",' ');
        /* cout << setw(printWidth) << right << "No lookuptable specified, use the default one" << endl; */
    } if (structRead.firstKeyExist("CAMERA")) { cameraName = structRead.getFirstLevel("CAMERA")[0]; /* cout << setw(printWidth) << right << "Choose to use the camera " << cameraName << endl; */ print.printVariable("Choose to use the camera",cameraName); if (structRead.secondKeyExist(cameraName,"FOCAL")) { istringstream(structRead.getSecondLevel(cameraName,"FOCAL")[0]) >> focalX >> focalY >> focalZ; /* cout << setw(printWidth) << right << "Camera focal point set to " << focalX << " " << focalY << " " <<focalZ << endl; */ print.printVariable("Camera focal point set to",focalX,focalY,focalZ); }else{ print.printVariable("Use default value for camera focal point",focalX,focalY,focalZ); /* cout << setw(printWidth) << right << "Use default value for camera focal point "<< focalX << " " << focalY << " " <<focalZ << endl; */ }

        if (structRead.secondKeyExist(cameraName,"POSITION")) {
            istringstream(structRead.getSecondLevel(cameraName,"POSITION")[0]) >> positionX >> positionY >> positionZ;
            /* cout << setw(printWidth) << right << "Camera position set to " << positionX << " " << positionY << " " <<positionZ << endl; */
            print.printVariable("Camera position set to",positionX,positionY,positionZ);
        }else{
            print.printVariable("USe default value for camera position",positionX,positionY,positionZ);
            /* cout << setw(printWidth) << right << "Use default value for camera position "<< positionX << " " << positionY << " " <<positionZ << endl; */
        }

        if (structRead.secondKeyExist(cameraName,"UP")) {
            istringstream(structRead.getSecondLevel(cameraName,"UP")[0]) >> upX >> upY >> upZ;
            print.printVariable("Camera up direction set to",upX,upY,upZ);
            /* cout << setw(printWidth) << right << "Camera up direction set to " << upX << " " << upY << " " <<upZ << endl; */
        }else{
            print.printVariable("Use default value for camera up direciton",upX,upY,upZ);
            /* cout << setw(printWidth) << right << "Use default value for camera up direction "<< upX << " " << upY << " " <<upZ << endl; */
        }
        if (structRead.secondKeyExist(cameraName,"CLIP")) {
            istringstream(structRead.getSecondLevel(cameraName,"CLIP")[1]) >> clipNear >> clipFar;
            print.printVariable("Camera clipping range",clipNear,clipFar);
            /* cout << setw(printWidth) << right << "Camera up direction set to " << upX << " " << upY << " " <<upZ << endl; */
        }else{
            print.printVariable("Use default value for camera up direciton",upX,upY,upZ);
            /* cout << setw(printWidth) << right << "Use default value for camera up direction "<< upX << " " << upY << " " <<upZ << endl; */
        }



    }else{
        print.printCenter("No camera specified, use the default one",' ');
        /* cout << setw(printWidth) << right << "No camera specified, use the default one" << endl; */
    }

    if (structRead.firstKeyExist("VISIBLE")) {
        istringstream temp(structRead.getFirstLevel("VISIBLE")[0]);
        while(temp >> number ) {
            domainVisibility[number] = true;
            /* cout << setw(printWidth) << right << "Visible domain label " << number << endl; */
            print.printVariable("Visible domain label",number);
        }
    }

    if (structRead.firstKeyExist("NOTVISIBLE")) {
        istringstream temp(structRead.getFirstLevel("NOTVISIBLE")[0]);
        while(temp >> number ) {
            domainVisibility[number] = false;
            /* cout << setw(printWidth) << right << "Invisible domain label " << number << endl; */
            print.printVariable("Invisible domain label",number);
        }
    }





    /* Start to visualize for each file */
    for (int m = 0; m < count; m++) {

    VTK_CREATE(vtkRenderer,renderer);
    VTK_CREATE(vtkRenderWindow,renWin);

    VTK_CREATE(vtkRenderWindowInteractor,iren);
    /* VTK_CREATE(vtkInteractorStyleTrackballCamera,style); */
    VTK_CREATE(CustomInteractorStyle,style);
    // Read the data
    VTK_CREATE(vtkXMLImageDataReader,reader);
    VTK_CREATE(vtkImageData,input);
    VTK_CREATE(vtkCamera,camera);


    VTK_CREATE(vtkColorTransferFunction,color);
    VTK_CREATE(vtkPiecewiseFunction,compositeOpacity);

    VTK_CREATE(vtkWindowToImageFilter,windowToImageFilter);
    VTK_CREATE(vtkPNGWriter,writer);


    style->setDatFile(imageName[m]);
    style->setVolumeOff();

        vector<vtkActor *> actorDomain;
        vector<vtkDataSetMapper *> domainMapper;
        for (int i = 0; i < domainTypeCount; i++) {
            actorDomain.push_back(vtkActor::New());        
            domainMapper.push_back(vtkDataSetMapper::New());        
        }



        /* cout << setw(printWidth) << right << " Visualizing file " << vtiFileName[m] << endl; */
        print.printVariable("Visualizing file",vtiFileName[m]);

        reader->SetFileName(vtiFileName[m].c_str());
        reader->Update();
        /* reader->Print(cout); */
        input->ShallowCopy(reader->GetOutput());



        /* Visualize each domain for one File */

        for (int i = 0; i < domainTypeCount; i++) {

            VTK_CREATE(vtkThreshold,domainThreshold);
            VTK_CREATE(vtkSmoothPolyDataFilter,domainSmooth);
            VTK_CREATE(vtkPolyDataNormals,normalGenerator);
            VTK_CREATE(vtkDataSetSurfaceFilter,domainSurface);


            domainThreshold->SetInputData(reader->GetOutput());

            /* cout << "Number of point array" << reader->GetNumberOfPointArrays() << reader->GetPointArrayStatus("domain")<< endl; */
            /* cout << "Number of cell array" << reader->GetNumberOfCellArrays() << endl; */
            domainThreshold->AllScalarsOff();
            domainThreshold->SetInputArrayToProcess(0,0,0,vtkDataObject::FIELD_ASSOCIATION_POINTS,"domain");
            /* cout << "Output domain of " << i << endl; */
            domainThreshold->ThresholdBetween(i-0.5,i+0.5);
            domainThreshold->Update();
            /* domainThreshold->Print(cout); */
            if(domainThreshold->GetOutput()->GetCells()->GetNumberOfCells() !=0){
                /* cout << "after threshold" << endl; */
                domainSurface->SetInputConnection(domainThreshold->GetOutputPort());
                domainSurface->Update();
                /* cout << "after surface" << endl; */


            domainSmooth->SetInputConnection(domainSurface->GetOutputPort());
            domainSmooth->SetNumberOfIterations(40);
            domainSmooth->SetRelaxationFactor(0.1);
            domainSmooth->FeatureEdgeSmoothingOff();
            domainSmooth->BoundarySmoothingOn();


                domainSmooth->Update();
                /* cout << "after smooth" << endl; */
                normalGenerator->SetInputConnection(domainSmooth->GetOutputPort());
                normalGenerator->ComputePointNormalsOn();
                normalGenerator->ComputeCellNormalsOn();
                normalGenerator->UpdateWholeExtent();
                actorDomain[i]->SetMapper(domainMapper[i]);

            domainMapper[i]->SetInputData( input );
            domainMapper[i]->SetInputConnection(normalGenerator->GetOutputPort());
            domainMapper[i]->ScalarVisibilityOff();


                domainMapper[i]->Update();
                actorDomain[i]->GetProperty()->SetColor(lookUpTable[i][0],lookUpTable[i][1],lookUpTable[i][2]);
                actorDomain[i]->GetProperty()->SetOpacity(lookUpTable[i][3]);
                /* cout << "domain visiblity " << i << " " << domainVisibility[i] << endl; */
                actorDomain[i]->SetVisibility(domainVisibility[i]);
                actorDomain[i]->Modified();
                /* actorDomain[i]->Print(cout) ; */
                renderer->AddActor(actorDomain[i]); 

            }
        }



        renWin->AddRenderer(renderer);
        /* renderer->Print(cout) ; */


        renderer->SetBackground(1,1,1);

        /* renWin->SetSize(600,600); */
        /* iren->Initialize(); */

        /* cout << "viewWindow" << viewWindow << renderer->VisibleActorCount() << endl; */

        camera->SetFocalPoint(focalX,focalY,focalZ);
        camera->SetPosition(positionX,positionY,positionZ);
        camera->SetViewUp(upX,upY,upZ);

        renderer->SetActiveCamera(camera);
        /* camera->Update(); */
        if (viewWindow) {
            /* renderer->ResetCamera(); */
            /* cout << setw(printWidth) << right << "Opening render window for " << fileName[m] << endl; */
            print.printVariable("Opening render window for",fileName[m]);
            iren->SetRenderWindow(renWin);
            renWin->SetSize(windowX,windowY);
            /* renderer->Render(); */
            renWin->Render();
            /* iren->SetDesiredUpdateRate(20); */
            iren->SetInteractorStyle(style);
            iren->Start();

        }else{
            renWin->SetSize(windowX,windowY);
            /* cout << setw(printWidth) << right << "Rendering off screen " << imageName[m] << endl; */
            print.printVariable("Rendering off screen",imageName[m]);
            renWin->SetOffScreenRendering(1);
            /* renderer->Render(); */
            renWin->Render();


            windowToImageFilter->SetInput(renWin);
            windowToImageFilter->Update();
            writer->SetFileName(imageName[m].c_str());
            writer->SetInputConnection(windowToImageFilter->GetOutputPort());
             writer->Write();
        }
    }

//    compositeOpacity->Delete();
//    color->Delete();
//
//    /* delete domainMapper []; */
//    reader->Delete();
//    renderer->Delete();
//    renWin->Delete();
//    iren->Delete();
//    style->Delete();
//

    print.printCenter("Program finished",'-');

    return 0;
}
