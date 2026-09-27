#include <vtkInteractorStyleTrackballCamera.h>
#include <vtkRenderWindowInteractor.h>
#include <string>

#ifndef CustomInteractorStyle_H
#define CustomInteractorStyle_H


class CustomInteractorStyle: public vtkInteractorStyleTrackballCamera{
    public:
        static CustomInteractorStyle* New();
        vtkTypeMacro(CustomInteractorStyle,vtkInteractorStyleTrackballCamera);

        void OnKeyPress() VTK_OVERRIDE;
        void OnChar() VTK_OVERRIDE;
        void setDatFile(std::string);
        void setVolumeOn();
        void setVolumeOff();
    protected:
        CustomInteractorStyle();
        ~CustomInteractorStyle();
    private:
        std::string datFileName;
        bool flag_volume;
};

#endif
