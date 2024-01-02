#include <CustomInteractorStyle.h>
#include <vtkWindowToImageFilter.h>
#include <vtkPNGWriter.h>
#include <vtkRenderWindow.h>
#include <vtkSmartPointer.h>
#include <FileNamer.h>
#include <vtkObjectFactory.h>
#include <vtkRenderer.h>
#include <vtkRendererCollection.h>
#include <vtkActorCollection.h>
#include <vtkActor.h>
#include <vtkMapper.h>
#include <vtkAbstractVolumeMapper.h>
#include <vtkCamera.h>

#define VTK_CREATE(type,name)\
    vtkSmartPointer<type> name = vtkSmartPointer<type>::New()


vtkStandardNewMacro(CustomInteractorStyle);

CustomInteractorStyle::CustomInteractorStyle(){
    flag_volume = false;
}

void CustomInteractorStyle::setVolumeOn(){
    flag_volume = true;
}

void CustomInteractorStyle::setVolumeOff(){
    flag_volume = false;
}

CustomInteractorStyle::~CustomInteractorStyle(){
}

void CustomInteractorStyle::OnChar(){

}

void CustomInteractorStyle::OnKeyPress(){
    /* std::cout << "in the on key press1" << std::endl; */
    vtkRenderWindowInteractor *rwi = this->Interactor;
    /* std::cout << "in the on key press2" << std::endl; */
    vtkRenderWindow* renWin=rwi->GetRenderWindow();
    /* std::cout << "in the on key press3" << std::endl; */
    vtkRenderer* renderer=renWin->GetRenderers()->GetFirstRenderer();
    /* std::cout << "in the on key press4" << std::endl; */
    vtkCamera* camera=renderer->GetActiveCamera();
    int key = int(rwi->GetKeySym()[0]);
    std::cout << "Pressed " << key << " "<<char(key) << std::endl;

    if (flag_volume) {
    /* std::cout << "in the on key press5" << std::endl; */
        vtkVolume* actor=static_cast<vtkVolume *>(renderer->GetVolumes()->GetItemAsObject(0));
    /* std::cout << "in the on key press55 " << renderer->GetVolumes()->GetNumberOfItems() <<  std::endl; */
    /* actor->Print(std::cout) ; */
        vtkAbstractVolumeMapper* mapper=actor->GetMapper();
    /* std::cout << "in the on key press555" << std::endl; */

        switch (key) {
            case 49:
            case 50:
            case 51:
            case 52:
            case 53:
            case 54:
            case 55:
            case 56:
            case 57:
                std::cout << "select array" << key-49 << endl;
                mapper->SelectScalarArray(key-49);
                break;
            case 48:
                mapper->SelectScalarArray(10);
                break;
        }
        mapper->Update();
        renWin->Render();



    }else{
        vtkActor* actor=renderer->GetActors()->GetLastActor();
        vtkMapper* mapper=actor->GetMapper();
    }

    /* std::cout << "in the on key press6" << std::endl; */
    switch (key) {
        case 115:{

                     std::string imageName;
                     VTK_CREATE(vtkWindowToImageFilter,windowToImageFilter);
                     VTK_CREATE(vtkPNGWriter,writer);

                     FileNamer name(datFileName);
                     imageName = name.autoNamer();
    std::cout << "Saving to file " << imageName.c_str() << std::endl;
    /* std::cout << "in the on key press8" << std::endl; */

                     renWin->SetOffScreenRendering(1);
                     renWin->Render();
                     windowToImageFilter->SetInput(renWin);
                     windowToImageFilter->Update();
                     writer->SetFileName(imageName.c_str());
                     writer->SetInputConnection(windowToImageFilter->GetOutputPort());
                     writer->Write();
                     renWin->SetOffScreenRendering(0);
                     break;}
        case 99:{
           // get the camera position;

                    double position[3],viewUp[3],focal[3];
                    camera->GetPosition(position);
                    camera->GetFocalPoint(focal);
                    camera->GetViewUp(viewUp);
                    std::cout.precision(4);
                    std::cout << "The camera position   : " << std::fixed << setw(10) << position[0];
                    std::cout << setw(10) <<position[1];
                    std::cout << setw(10) <<position[2] << std::endl;
                    std::cout << "The camera focal point: " << std::fixed << setw(10) << focal[0];
                    std::cout << setw(10) <<focal[1];
                    std::cout << setw(10) <<focal[2] << std::endl;
                    std::cout << "The camera view up    : " << std::fixed << setw(10) << viewUp[0] ;
                    std::cout << setw(10) <<viewUp[1] ;
                    std::cout << setw(10) <<viewUp[2] << std::endl;
                }
    }

}

void CustomInteractorStyle::setDatFile(std::string filename){
    datFileName = filename;
}
