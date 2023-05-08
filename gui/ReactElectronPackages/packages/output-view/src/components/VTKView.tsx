import React, { Component } from "react";
import "./VTKView.less";
import "@kitware/vtk.js/Rendering/Profiles/All";
import { Vector3 } from "@kitware/vtk.js/types";
import Constants from "@kitware/vtk.js/Rendering/Core/ImageMapper/Constants";
import vtkVolume from "@kitware/vtk.js/Rendering/Core/Volume";
import vtkVolumeMapper from "@kitware/vtk.js/Rendering/Core/VolumeMapper";
import vtkImageMapper from "@kitware/vtk.js/Rendering/Core/ImageMapper";
import vtkImageSlice from "@kitware/vtk.js/Rendering/Core/ImageSlice";
import vtkXMLImageDataReader from "@kitware/vtk.js/IO/XML/XMLImageDataReader";
// import vtkColorMaps from "@kitware/vtk.js/Rendering/Core/ColorTransferFunction/ColorMaps";
import vtkColorMaps from "./ColorMaps.json";
import vtkImageData from "@kitware/vtk.js/Common/DataModel/ImageData";

const presetMap = Object.create(null);

vtkColorMaps
  .filter((p) => p.RGBPoints)
  .filter((p) => p.ColorSpace !== "CIELAB")
  .forEach((p) => {
    presetMap[p.Name] = p;
  });

function getPresetByName(name: string) {
  return presetMap[name];
}
import vtkColorTransferFunction from "@kitware/vtk.js/Rendering/Core/ColorTransferFunction";
import vtkPiecewiseFunction from "@kitware/vtk.js/Common/DataModel/PiecewiseFunction";
import vtkOrientationMarkerWidget from "@kitware/vtk.js/Interaction/Widgets/OrientationMarkerWidget";
import vtkAxesActor from "@kitware/vtk.js/Rendering/Core/AxesActor";

import vtkOutlineFilter from "@kitware/vtk.js/Filters/General/OutlineFilter";

// import vtkFullScreenRenderWindow from "@kitware/vtk.js/Rendering/Misc/FullScreenRenderWindow";
import vtkGenericRenderWindow from "@kitware/vtk.js/Rendering/Misc/GenericRenderWindow";
// import vtkFullScreenRenderWindow from "@kitware/vtk.js/Rendering/Misc/FullScreenRenderWindow";
import * as vtkMath from "@kitware/vtk.js/Common/Core/Math";
import vtkMapper from "@kitware/vtk.js/Rendering/Core/Mapper";
import vtkActor from "@kitware/vtk.js/Rendering/Core/Actor";
import { Viz3DContext, Viz3DActionType } from "../contexts/Viz3DContext";
import vtkDataArray from "@kitware/vtk.js/Common/Core/DataArray";

const { SlicingMode } = Constants;
const path = require("path");
const ipcRenderer = window.require("electron").ipcRenderer;

interface VTKViewState {
  count: number;
  imgList: string[];
  w: number;
  h: number;
  initial: boolean;
}

interface VTKView3DPipeline {
  fullScreenRenderer: vtkGenericRenderWindow;
  axes: vtkAxesActor;
  actor: vtkVolume;
  mapper: vtkVolumeMapper;
  outline: vtkOutlineFilter;
  outlineActor: vtkActor;
  outlineMapper: vtkMapper;
  lookupTable: vtkColorTransferFunction;
  piecewiseFunction: vtkPiecewiseFunction;
  vtiReader: vtkXMLImageDataReader;
}

interface VTKView2DPipeline {
  fullScreenRenderer: vtkGenericRenderWindow;
  lookupTable: vtkColorTransferFunction;
  piecewiseFunction: vtkPiecewiseFunction;
  axes: vtkAxesActor;
  actor: vtkImageSlice;
  mapper: vtkImageMapper;
  vtiReader: vtkXMLImageDataReader;
}

type VTKViewPipeline = VTKView2DPipeline | VTKView3DPipeline;

const defaultVTKViewPipeline: VTKViewPipeline = {
  fullScreenRenderer: vtkGenericRenderWindow.newInstance({
    background: [0.157, 0.172, 0.204],
  }),
  lookupTable: vtkColorTransferFunction.newInstance(),
  piecewiseFunction: vtkPiecewiseFunction.newInstance(),
  axes: vtkAxesActor.newInstance(),
  actor: vtkVolume.newInstance(),
  mapper: vtkVolumeMapper.newInstance(),
  outline: vtkOutlineFilter.newInstance(),
  outlineActor: vtkActor.newInstance(),
  outlineMapper: vtkMapper.newInstance(),
  vtiReader: vtkXMLImageDataReader.newInstance(),
};

function getSameTypeFilesInList(
  fileName: string,
  fl: string[]
): [number, string[]] {
  let tempList: string[] = [];
  let count = 0;
  for (let index = 0; index < fl.length; index++) {
    const element = fl[index];
    if (element.includes(fileName!.split(".")[0])) {
      count = count + 1;
      tempList.push(fl[index]);
    }
  }
  return [count, tempList];
}

class VTKView extends React.Component<{}, VTKViewState> {
  static contextType = Viz3DContext;
  declare context: React.ContextType<typeof Viz3DContext>;

  container: React.RefObject<HTMLDivElement>;
  pipeline: VTKViewPipeline;
  state: VTKViewState;
  is2D: boolean;

  constructor(props: {}) {
    super(props);
    this.container = React.createRef();
    this.pipeline = defaultVTKViewPipeline;
    this.state = {
      count: 0,
      imgList: [],
      w: 0,
      h: 0,
      initial: true,
    };
    this.pipeline.fullScreenRenderer.setContainer(
      this.container.current as HTMLElement
    );
    this.pipeline.fullScreenRenderer.resize();
    this.is2D = false;
  }

  getComponentCountNamesSelected = (vtiReader: vtkXMLImageDataReader) => {
    const source = vtiReader.getOutputData(0);
    let componentNames: string[] = [];
    source
      .getPointData()
      .getArrays()
      .forEach((element: vtkDataArray) => {
        componentNames.push(element.getName());
      });
    return {
      componentCount: source.getPointData().getNumberOfArrays(),
      componentNames: componentNames,
      selectedComponent: componentNames[0],
    };
  };
  readXMLImageDataFromString = (result: string) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsArrayBuffer(new Blob([result]));
      const vtiReader = vtkXMLImageDataReader.newInstance();
      console.log("before read", this.context.state);

      reader.onload = (e) => {
        console.log("VTKView::updatePipeline::reader.onload", this.state);
        vtiReader.parseAsArrayBuffer(reader.result as ArrayBuffer);
        const source = vtiReader.getOutputData(0);
        this.context.dispatch({
          type: Viz3DActionType.Update,
          payload: {
            ...this.getComponentCountNamesSelected(vtiReader),
          },
        });

        const dataExtent = source.getExtent();
        this.is2D = false;
        if (
          dataExtent[1] === dataExtent[0] ||
          dataExtent[3] === dataExtent[2] ||
          dataExtent[5] === dataExtent[4]
        ) {
          this.is2D = true;
        }
        resolve(vtiReader);
      };
    });
  };

  readData = (filePath: string) => {
    console.log("VTKView:readData:filePath", filePath);
    return new Promise((resolve, reject) => {
      if (filePath === "" || filePath === undefined || filePath === ".") {
        this.readXMLImageDataFromString(this.context.state.fileContent!).then(
          (vtiReader) => {
            console.log("after read", this.context.state);
            resolve(vtiReader);
          }
        );
      } else {
        if (this.context.state.fileChanged) {
          console.log();
          ipcRenderer.invoke("readFile", filePath).then((result: string) => {
            this.readXMLImageDataFromString(result).then((vtiReader) => {
              resolve(vtiReader);
            });
          });
        }
      }
    });
  };

  visualize = () => {
    this.readData(
      path.join(this.context.state.fileLoc, this.context.state.fileName)
    ).then((vtiReader) => {
      if (this.is2D) {
        // visualize for 2D
        this.visualize2D(vtiReader as vtkXMLImageDataReader);
      } else {
        // visualize for 3D
        this.visualize3D(vtiReader as vtkXMLImageDataReader);
      }
    });
  };

  visualize2D = (vtiReader: vtkXMLImageDataReader) => {
    const component = this.getComponentCountNamesSelected(vtiReader);
    let selectedComponent = this.context.state.selectedComponent;
    if (selectedComponent === "" || selectedComponent === undefined) {
      selectedComponent = component.componentNames![0];
    }

    this.pipeline = this.pipeline as VTKView2DPipeline;

    const source = (vtiReader as vtkXMLImageDataReader).getOutputData(0);
    const dataArray = source.getPointData().getArrays()[selectedComponent];
    const dataRange: [number, number] = dataArray.getRange();
    const dataExtent = source.getExtent();

    source
      .getPointData()
      .setScalars(source.getPointData().getArrayByName(selectedComponent));

    const renderer = this.pipeline.fullScreenRenderer.getRenderer();
    const renderWindow = this.pipeline.fullScreenRenderer.getRenderWindow();

    // set mapper
    this.pipeline.mapper = vtkImageMapper.newInstance({
      sliceAtFocalPoint: true,
    });
    this.pipeline.mapper.setInputData(vtiReader.getOutputData(0));
    if (dataExtent[0] === dataExtent[1]) {
      this.pipeline.mapper.setISlice(0);
    } else if (dataExtent[2] === dataExtent[3]) {
      this.pipeline.mapper.setJSlice(0);
    } else if (dataExtent[4] === dataExtent[5]) {
      this.pipeline.mapper.setKSlice(0);
    }

    // set actor
    this.pipeline.actor = vtkImageSlice.newInstance({
      mapper: this.pipeline.mapper,
    });

    // lookuptable
    this.pipeline.lookupTable.applyColorMap(
      getPresetByName("erdc_rainbow_bright")
    );
    this.pipeline.lookupTable.setMappingRange(...dataRange);
    this.pipeline.lookupTable.updateRange();
    this.pipeline.actor
      .getProperty()
      .setRGBTransferFunction(0, this.pipeline.lookupTable);
    this.pipeline.actor.getProperty().setInterpolationTypeToLinear();

    this.pipeline.piecewiseFunction.removeAllPoints();
    this.pipeline.piecewiseFunction.addPoint(dataRange[0], 1);
    this.pipeline.actor
      .getProperty()
      .setScalarOpacity(0, this.pipeline.piecewiseFunction);

    renderer.addActor(this.pipeline.actor);
    renderer.resetCamera();
    renderWindow.render();

    // set camera
    const camera = renderer.getActiveCamera();
    const position = camera.getFocalPoint();
    // offset along the slicing axis
    const normal = (
      this.pipeline as VTKView2DPipeline
    ).mapper.getSlicingModeNormal();
    position[0] += normal[0];
    position[1] += normal[1];
    position[2] += normal[2];
    camera.setPosition(...position);
    camera.setViewUp(
      (
        this.pipeline as VTKView2DPipeline
      ).mapper.getSlicingModeNormal() as Vector3
    );
    renderer.resetCamera();
  };

  visualize3D = (vtiReader: vtkXMLImageDataReader) => {
    const component = this.getComponentCountNamesSelected(vtiReader);

    let selectedComponent = this.context.state.selectedComponent;
    if (selectedComponent === "" || selectedComponent === undefined) {
      selectedComponent = component.componentNames![0];
    }

    this.pipeline = this.pipeline as VTKView3DPipeline;
    const source = (vtiReader as vtkXMLImageDataReader).getOutputData(0);

    const dataArray = source.getPointData().getArrayByName(selectedComponent);
    const dataRange: [number, number] = dataArray.getRange();

    source
      .getPointData()
      .setScalars(source.getPointData().getArrayByName(selectedComponent));
    const renderer = this.pipeline.fullScreenRenderer.getRenderer();
    const renderWindow = this.pipeline.fullScreenRenderer.getRenderWindow();

    this.pipeline.mapper = vtkVolumeMapper.newInstance();
    this.pipeline.actor = vtkVolume.newInstance();
    this.pipeline.actor.setMapper(this.pipeline.mapper);
    this.pipeline.mapper.setInputData(source);

    this.pipeline.outline = vtkOutlineFilter.newInstance();
    this.pipeline.outlineActor = vtkActor.newInstance();
    this.pipeline.outlineMapper = vtkMapper.newInstance();
    this.pipeline.outline.setInputConnection(vtiReader.getOutputPort(0));
    this.pipeline.outlineMapper.setInputConnection(
      this.pipeline.outline.getOutputPort(0)
    );
    this.pipeline.outlineActor.setMapper(this.pipeline.outlineMapper);
    this.pipeline.outlineActor.getProperty().set({ lineWidth: 5 });

    renderer.addVolume(this.pipeline.actor);
    renderer.addActor(this.pipeline.outlineActor);

    this.pipeline.lookupTable.applyColorMap(
      getPresetByName("erdc_rainbow_bright")
    );
    this.pipeline.lookupTable.setMappingRange(...dataRange);
    this.pipeline.lookupTable.updateRange();
    this.pipeline.actor
      .getProperty()
      .setRGBTransferFunction(0, this.pipeline.lookupTable);
    this.pipeline.actor.getProperty().setInterpolationTypeToLinear();

    this.pipeline.piecewiseFunction.removeAllPoints();

    this.pipeline.piecewiseFunction.addPoint(dataRange[0], 0);
    this.pipeline.piecewiseFunction.addPoint(
      (dataRange[0] + dataRange[1]) * 0.5,
      0.1
    );
    this.pipeline.piecewiseFunction.addPoint(dataRange[1], 1);
    this.pipeline.actor
      .getProperty()
      .setScalarOpacity(0, this.pipeline.piecewiseFunction);

    renderer.resetCamera();

    renderWindow.render();
    const axes = vtkAxesActor.newInstance();

    const orientationWidget = vtkOrientationMarkerWidget.newInstance({
      actor: axes,
      interactor: renderWindow.getInteractor(),
    });

    // // green is z, yellow is y, red is x
    orientationWidget.setEnabled(true);
    orientationWidget.setViewportCorner(
      vtkOrientationMarkerWidget.Corners.BOTTOM_LEFT
    );
    orientationWidget.setViewportSize(0.15);
    orientationWidget.setMinPixelSize(100);
    orientationWidget.setMaxPixelSize(300);
  };

  componentDidMount() {
    console.log("vtk mounted", this.context.state, this.state);

    // create axes
    const orientationWidget = vtkOrientationMarkerWidget.newInstance({
      actor: this.pipeline.axes,
      interactor: this.pipeline.fullScreenRenderer
        .getRenderWindow()
        .getInteractor(),
    });

    orientationWidget.setEnabled(true);
    orientationWidget.setViewportCorner(
      vtkOrientationMarkerWidget.Corners.BOTTOM_LEFT
    );
    orientationWidget.setViewportSize(0.15);
    orientationWidget.setMinPixelSize(100);
    orientationWidget.setMaxPixelSize(300);

    this.pipeline.fullScreenRenderer.setContainer(
      this.container.current as HTMLElement
    );
    this.pipeline.fullScreenRenderer.resize();

    this.visualize();
  }

  captureCurrentScene = (filePath: string) => {
    this.pipeline.fullScreenRenderer
      .getRenderWindow()
      .getViews()[0]
      .captureNextImage()
      .then(function (result: string) {
        ipcRenderer.invoke(
          "writeFile",
          filePath,
          result.replace(/^data:image\/\w+;base64,/, "")
        );
      })
      .then();
    this.pipeline.fullScreenRenderer.getRenderWindow().render();
    this.context.dispatch({
      type: Viz3DActionType.Update,
      payload: {
        exportScene: false,
      },
    });
  };

  componentDidUpdate() {
    if (this.context.state.exportScene) {
      ipcRenderer.invoke("obtainImage").then((filePath: string) => {
        console.log(
          "VTKView::componentDidUpdate::exportScene::filePath",
          filePath
        );
        this.captureCurrentScene(filePath);
      });
    }

    if (this.context.state.exportGIF) {
      console.log("VTKView::componentDidUpdate::exportGIF");
      ipcRenderer
        .invoke("obtainGIF")
        .then((filePath: string) => {
          this.context.dispatch({
            type: Viz3DActionType.Update,
            payload: {
              exportGIF: false,
            },
          });
          this.setState({
            w: this.pipeline.fullScreenRenderer
              .getRenderWindow()
              .getViews()[0]
              .getContext().drawingBufferWidth,
            h: this.pipeline.fullScreenRenderer
              .getRenderWindow()
              .getViews()[0]
              .getContext().drawingBufferHeight,
          });

          let [count, tempList] = getSameTypeFilesInList(
            this.context.state.fileName!,
            this.context.state.fileList!
          );

          this.setState({
            count: count,
          });

          console.log("this state count", this.state.count);
          for (let index = 0; index < count; index++) {
            setTimeout(() => {
              const element = tempList[index];
              console.log(element);
              this.readData(path.join(this.context.state.fileLoc, element))
                .then(() => {
                  this.visualize();
                  this.captureCurrentScene(
                    path.join(
                      this.context.state.fileLoc,
                      element,
                      index + ".png"
                    )
                  );
                })
                .then(() => {
                  this.context.dispatch({
                    type: Viz3DActionType.AddExport,
                  });
                });
            }, 1000 * index);
          }
          console.log("the filepath", filePath);
          return filePath;
          // }
        })
        .then((filePath: string) => {
          // setTimeout(() => {
          ipcRenderer.invoke("writeGIF", {
            filePath: filePath,
            width: this.state.w,
            height: this.state.h,
            imgList: this.state.imgList,
          });
          // }, 1000 * this.state.count);
          this.setState({ count: 0 });
          this.context.dispatch({
            type: Viz3DActionType.Update,
            payload: {
              exportCount: 0,
            },
          });
        });
    }

    if (this.context.state.loadData) {
      console.log("VTKView::componentDidUpdate::fileChanged", this);
      this.visualize();
      this.context.dispatch({
        type: Viz3DActionType.ResetChange,
      });
    }
  }

  render() {
    return <div className="VTKView" ref={this.container}></div>;
  }
}

export { VTKView };
