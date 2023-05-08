import React from "react";
import { Row, Col, Form, Button, message, FormInstance } from "antd";
import "./parameterInput.less";
// import SystemDimension from "./input/dimension/systemDimension";
// import StructureInput from "./input/structureInput/structureInput";
// import StartStopControl from "./input/startStopControl/StartStopControl";
// import InputControl from "./input/inputControl/InputControl";
// import OutputInput from "./input/outputInput/OutputInput";
import { NameInput } from "@mupro/input-form/src/components/NameInput";
import { DimensionInput } from "@mupro/input-form/src/components/DimensionInput";
import { StructureInput } from "@mupro/input-form/src/components/StructureInput";
import { StartStopControl } from "@mupro/start-stop-control/src";
import { OutputInput } from "@mupro/input-form/src/components/OutputInput";
import { SystemInput } from "./SystemInput";
import type { PreferenceValue } from "@mupro/main-process/src/main-process";
import { fixStructureInterfaceFormat } from "@mupro/typings/StructureInput";
import { fixPhaseInterfaceFormat } from "@mupro/typings/PhaseInput";
import type { DimensionInputData } from "@mupro/typings/DimensionInput";
import { defaultDimensionInput } from "@mupro/typings/DimensionInput";
import { defaultStructureXMLInput } from "@mupro/typings/StructureInput";
import { defaultOutputInput } from "@mupro/typings/OutputInput";
import type {
  SystemData as SystemInputData,
  // SystemImport as SystemInputImport,
} from "./typings";
import { defaultSystem as defaultSystemInput } from "./typings";
import type { OutputInputData } from "@mupro/typings/OutputInput";
import type { StructureInputData } from "@mupro/typings/StructureInput";
import { marginBottom } from "@mupro/typings/Constants";
const ipcRenderer = window.require("electron").ipcRenderer;

interface ParameterInputProps {}

interface ParameterInputState {
  fileLocation: string;
  preferences: PreferenceValue;
  dimension: DimensionInputData;
  system: SystemInputData;
  output: OutputInputData;
  structure: StructureInputData;
}

interface ImportData {
  location: string;
  file: any;
}

function fixSystemInterfaceFormat(system: any) {
  fixPhaseInterfaceFormat(system.solver.ref);
  if (!Array.isArray(system.material.phase)) {
    system.material.phase = [system.material.phase];
  }
  system.material.phase.forEach((phase: any) => {
    fixPhaseInterfaceFormat(phase);
  });
}
class ParameterInput extends React.Component<
  ParameterInputProps,
  ParameterInputState
> {
  formRef: React.RefObject<FormInstance>;
  nameRef: React.RefObject<NameInput>;
  dimensionRef: React.RefObject<DimensionInput>;
  outputRef: React.RefObject<OutputInput>;
  systemRef: React.RefObject<SystemInput>;
  structureRef: React.RefObject<StructureInput>;
  controlRef: React.RefObject<StartStopControl>;
  state: ParameterInputState;

  constructor(props: ParameterInputProps) {
    super(props);
    this.formRef = React.createRef();
    this.nameRef = React.createRef();
    this.dimensionRef = React.createRef();
    this.outputRef = React.createRef();
    this.systemRef = React.createRef();
    this.structureRef = React.createRef();
    this.controlRef = React.createRef();
    this.state = {
      fileLocation: "",
      preferences: {
        hide_basic: false,
        hide_material: false,
        hide_structure: false,
      },
      dimension: defaultDimensionInput,
      system: defaultSystemInput,
      output: defaultOutputInput,
      structure: defaultStructureXMLInput,
    };
  }

  componentDidMount() {
    ipcRenderer.invoke("loadPreferences").then((result: PreferenceValue) => {
      console.log("main preferences did mount ", result);
      if (typeof result == "undefined") {
        this.setState({
          preferences: {
            hide_basic: false,
            hide_material: false,
            hide_structure: false,
          },
        });
      } else {
        this.setState({ preferences: result });
      }
    });
    console.log(
      "parameterInput componentDidMount",
      this.dimensionRef,
      this.outputRef,
      this.systemRef,
      this.structureRef
    );
    ipcRenderer.on("importFile", (event: Event, message: ImportData) => {
      console.log(
        "import for parameter input",
        message,
        this.dimensionRef,
        this.outputRef,
        this.systemRef,
        this.structureRef
      );
      this.onImport(message);
    });
  }

  componentDidUpdate() {
    console.log(
      "componentDidUpdate parameterInput",
      this.dimensionRef,
      this.outputRef,
      this.systemRef,
      this.structureRef
    );
  }

  onImport = (message: ImportData) => {
    console.log(
      "ParameterInput::onImport",
      this.dimensionRef,
      this.outputRef,
      this.systemRef,
      this.structureRef
    );
    fixStructureInterfaceFormat(message.file.input.structure);
    fixSystemInterfaceFormat(message.file.input.system);

    this.nameRef.current!.onImport(message.file.input.name);
    this.dimensionRef.current!.onImport(message.file.input.dimension);
    this.outputRef.current!.onImport(message.file.input.output);
    this.systemRef.current!.onImport(message.file.input.system);
    this.structureRef.current!.onImport(message.file.input.structure);
  };
  onFinish = (values: any) => {
    console.log("finish of the parameter input", values);
    ipcRenderer.invoke("saveFile").then((result: string) => {
      console.log("saving file", result);
      if (typeof result == "undefined") {
        console.log("The input directory is undefined");
        return Promise.reject("The input directory is undefined");
      }
      console.log(result, this.state.fileLocation);
      // console.log(this);
      this.setState({ fileLocation: result }, () => {
        let name = this.nameRef.current!.onFinish();
        let dimension = this.dimensionRef.current!.onFinish();
        let structure = this.structureRef.current!.onFinish();
        console.log("finish test", dimension, structure);
        let output = this.outputRef.current!.onFinish();
        let system = this.systemRef.current!.onFinish();

        if (this.state.fileLocation) {
          console.log("simconfig", this.state);
          ipcRenderer
            .invoke("writeInput", {
              fileLocation: this.state.fileLocation,
              input: {
                name: name,
                dimension: dimension,
                output: output,
                system: system,
                structure: structure,
              },
            })
            .then(() => {
              console.log("after wrute");
              message.info(
                "input.xml file generated! to " + this.state.fileLocation,
                5
              );
            });
        } else {
          ipcRenderer
            .invoke(
              "messageBox",
              "You must select a folder to store the input files first"
            )
            .then(() => {
              console.log("after no file locatin");
            });
        }
      });
    });
  };

  render() {
    console.log("The parameter ", this.state.preferences);
    return (
      <Col flex="400px" className="input-panel">
        <Row justify="space-around">
          <div
            className={this.state.preferences.hide_basic ? "hide" : "normal"}
          >
            <NameInput ref={this.nameRef} />
            <DimensionInput ref={this.dimensionRef} />
            <OutputInput ref={this.outputRef} noFrequency />
          </div>
          <div
            className={this.state.preferences.hide_material ? "hide" : "normal"}
          >
            <SystemInput ref={this.systemRef} />
          </div>
          <div
            className={
              this.state.preferences.hide_structure ? "hide" : "normal"
            }
          >
            <StructureInput ref={this.structureRef} />
          </div>

          <Form
            ref={this.formRef}
            onFinish={this.onFinish}
            labelCol={{ span: 8 }}
            wrapperCol={{ span: 16 }}
            style={{ width: "100%" }}
          >
            {/* <InputControl formRef={this.formRef} ref={this.controlRef}/> */}
            <Form.Item
              label=" "
              colon={false}
              style={{ textAlign: "right", marginBottom: marginBottom }}
            >
              <Button type="primary" htmlType="submit" style={{ width: 130 }}>
                Create inputs
              </Button>
            </Form.Item>
          </Form>
        </Row>

        <StartStopControl fileLocation={this.state.fileLocation} />
      </Col>
    );
  }
}

export { ParameterInput };
