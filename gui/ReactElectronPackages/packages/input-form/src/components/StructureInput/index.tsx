import React from "react";
import {
  Button,
  Input,
  Form,
  Tooltip,
  Tabs,
  Row,
  Select,
  Switch,
  FormInstance,
} from "antd";
import { GeometryInput } from "./Geometry/geometryInput";
import "./index.less";
import { EditableTagGroup } from "./EditableTagGroup";
const { Option } = Select;
const { TabPane } = Tabs;
import type { GeometryInputData } from "@mupro/typings/GeometryInput";
import type {
  StructureInputXMLData,
  StructureInputData,
  StructureInputDATData,
  StructureInputDream3DData,
} from "@mupro/typings/StructureInput";
import {
  defaultStructureDATInput,
  defaultStructureXMLInput,
} from "@mupro/typings/StructureInput";
import { marginBottom } from "@mupro/typings/Constants";
const ipcRenderer = window.require("electron").ipcRenderer;

interface StructureInputState {
  geometryCount: number;
  sourceType: "empty" | "xml" | "vti" | "dat" | "dream3d";
  matrixLabel: string;
  dataType: "continuous" | "discrete";
  structureFile: string;
}

interface StructureInputProps {
  title: string;
}

class StructureInput extends React.Component<
  StructureInputProps,
  StructureInputState
> {
  formRef: React.RefObject<FormInstance>;
  tagRef: React.RefObject<EditableTagGroup>;
  geometryRefList: React.RefObject<GeometryInput>[];
  state: StructureInputState;

  constructor(props: StructureInputProps) {
    super(props);
    this.geometryRefList = [];
    this.formRef = React.createRef();
    this.tagRef = React.createRef();
    this.state = {
      geometryCount: 0,
      sourceType: "empty",
      matrixLabel: "0",
      dataType: "discrete",
      structureFile: "microstructure.in",
    };
  }

  onImport = (structure: StructureInputData) => {
    if (!this.formRef.current) return;
    console.log("onImport from the input-form-structure", structure);
    this.geometryRefList = [];
    if (structure.sourceType.trim() === "xml") {
      structure = structure as StructureInputXMLData;
      for (let index = 0; index < structure.geometry.length; index++) {
        this.geometryRefList.push(React.createRef());
      }
      this.setState(
        {
          geometryCount: structure.geometry.length,
          matrixLabel: structure.matrixLabel.trim(),
          sourceType: structure.sourceType,
        },
        () => {
          structure = structure as StructureInputXMLData;
          this.formRef.current!.setFieldsValue({
            matrixLabel: structure.matrixLabel.trim(),
            sourceType: structure.sourceType.trim(),
          });
          for (let index = 0; index < this.state.geometryCount; index++) {
            this.geometryRefList[index].current!.onImport(
              structure.geometry[index]
            );
          }
        }
      );
    } else if (structure.sourceType.trim() === "dream3d") {
      structure = structure as StructureInputDream3DData;

      this.setState({
        sourceType: structure.sourceType,
        structureFile: structure.file,
      });

      this.formRef.current!.setFieldsValue({
        sourceType: structure.sourceType.trim(),
        structureFile: structure.file,
      });
    } else {
      structure = structure as StructureInputDATData;
      this.setState(
        {
          sourceType: structure.sourceType,
          dataType: structure.dataType,
          structureFile: structure.file,
        },
        () => {
          structure = structure as StructureInputDATData;
          this.formRef.current!.setFieldsValue({
            sourceType: structure.sourceType.trim(),
            structureDataType: structure.dataType,
            structureFile: structure.file,
          });
          if (structure.dataType === "continuous") {
            if (this.tagRef.current) {
              this.tagRef.current.onImport(structure.keypoints);
            }
          }
        }
      );
    }
  };

  onFinish = (): StructureInputData => {
    if (!this.formRef.current) return defaultStructureXMLInput;
    let values = this.formRef.current.getFieldsValue(true);
    console.log("StructureInput::onFinish::state", this.state);
    console.log("StructureInput::onFinish::values", values);
    if (this.state.sourceType === "xml") {
      let geometryList: GeometryInputData[] = [];
      for (var i = 0; i < this.state.geometryCount; i++) {
        geometryList.push(this.geometryRefList[i].current!.onFinish(values)!);
      }
      return {
        matrixLabel: values.matrixLabel,
        sourceType: values.sourceType,
        geometry: geometryList,
      };
    } else if (this.state.sourceType === "dream3d") {
      return {
        sourceType: values.sourceType,
        file: values.structureFile,
      };
    } else {
      if (this.state.dataType === "discrete") {
        return {
          sourceType: values.sourceType,
          dataType: this.state.dataType,
          file: values.structureFile,
        };
      } else {
        if (!this.tagRef.current) return defaultStructureDATInput;
        return {
          sourceType: values.sourceType,
          dataType: this.state.dataType,
          file: values.structureFile,
          keypoints: {
            value: this.tagRef.current.onFinish(),
          },
        };
      }
    }
  };

  onSelectSourceType = (value: "xml" | "vti" | "dat" | "dream3d") => {
    console.log("source type changed ", value);
    this.setState({
      sourceType: value,
      dataType: "discrete",
    });
    // this.props.handleSourceTypeChanged(value);
  };

  getSelectSourceType = () => {
    if (!this.formRef.current) return;
    console.log("Get the selected source type");
    return this.formRef.current.getFieldsValue()["sourceType"];
  };

  add = () => {
    console.log("the geometry add ", this.state.geometryCount);
    this.setState({ geometryCount: this.state.geometryCount + 1 });
    this.geometryRefList.push(React.createRef());
  };

  remove = (targetKey: string) => {
    if (this.state.geometryCount === 0) {
      console.log("remove geometry ", this.state.geometryCount);
    } else {
      this.setState({ geometryCount: this.state.geometryCount - 1 });
      this.geometryRefList.splice(Number(targetKey), 1);
    }
  };

  onEdit = (
    targetKey:
      | string
      | React.MouseEvent<Element, MouseEvent>
      | React.KeyboardEvent<Element>,
    action: "add" | "remove"
  ) => {
    if (action === "add") {
      this.add();
    } else {
      this.remove(targetKey as string);
    }
  };

  onDataTypeChange = (value: "continuous" | "discrete") => {
    console.log("Toggle the data type", value);

    this.setState({
      dataType: value,
    });
  };

  onSelectStructureFile = () => {
    ipcRenderer.invoke("selectFile").then((result: string) => {
      this.formRef.current?.setFieldValue("structureFile", result);
      this.setState({
        structureFile: result,
      });
    });
  };

  render() {
    const formstyle = {
      labelCol: { span: 8 },
      wrapperCol: { span: 16 },
      style: { width: "100%" },
    };
    const formItemStyle = {
      style: { marginBottom: marginBottom },
    };
    return (
      <Form {...formstyle} ref={this.formRef}>
        <h3>{this.props.title}</h3>
        <Form.Item label="Source type" colon={false} {...formItemStyle}>
          <Form.Item name="sourceType" colon={false} noStyle>
            <Select
              placeholder="Select a file"
              optionFilterProp="children"
              onChange={this.onSelectSourceType}
              // ref={this.sourceSelectRef}
            >
              <Option value="xml">Generate from xml file</Option>
              <Option value="vti">Read from vti</Option>
              <Option value="dat">Read from dat</Option>
              <Option value="dream3d">Read from dream3d ascii export</Option>
            </Select>
          </Form.Item>
        </Form.Item>

        {this.state.sourceType === "vti" ||
        this.state.sourceType === "dat" ||
        this.state.sourceType === "dream3d" ? (
          <>
            <div
              style={{
                width: "33%",
                textAlign: "right",
                paddingRight: "10px",
                display: "inline-block",
                margin: "0px",
              }}
            >
              <Button type="primary" onClick={this.onSelectStructureFile}>
                Select File
              </Button>
            </div>
            <Form.Item noStyle name="structureFile">
              <Input
                placeholder="Location"
                style={{ width: "67%", marginBottom: marginBottom }}
              />
            </Form.Item>
          </>
        ) : null}
        {this.state.sourceType === "vti" || this.state.sourceType === "dat" ? (
          <>
            {/* <h3>Data type</h3> */}
            <Form.Item
              label="Data Type"
              name="structureDataType"
              {...formItemStyle}
            >
              <Select
                placeholder="Select the tensor symmetry"
                onChange={this.onDataTypeChange}
              >
                <Option value="continuous">Continuous</Option>
                <Option value="discrete">Discrete</Option>
              </Select>
            </Form.Item>
            {/* <p>{this.state.dataType}</p> */}
            {this.state.dataType === "continuous" ? (
              <Form.Item name="keypoints" label="Keys" {...formItemStyle}>
                <EditableTagGroup ref={this.tagRef} />
              </Form.Item>
            ) : null}
          </>
        ) : null}

        <div
          className="geometryDefine"
          style={
            this.state.sourceType === "xml"
              ? { display: "block" }
              : { display: "none" }
          }
        >
          <Form.Item
            label=" "
            colon={false}
            style={{
              textAlign: "right",
              width: "100%",
              marginBottom: marginBottom,
            }}
            labelCol={{ span: 8 }}
            wrapperCol={{ span: 16 }}
          >
            <Button style={{ width: "100%" }} onClick={this.add}>
              Add Geometry
            </Button>
          </Form.Item>
          <Form.Item label="Default label" {...formItemStyle}>
            <Tooltip
              title="The label for matrix, which is the area outside of the define geometry"
              placement="bottomLeft"
            >
              <Form.Item
                name="matrixLabel"
                noStyle
                rules={[
                  {
                    message: "The matrix phase label is required",
                  },
                ]}
              >
                <Input
                  placeholder={this.state.matrixLabel}
                  style={{ width: "33%" }}
                />
              </Form.Item>
            </Tooltip>
          </Form.Item>

          {this.state.geometryCount > 0 ? (
            <Tabs
              hideAdd
              defaultActiveKey="1"
              tabPosition="top"
              type="editable-card"
              onEdit={this.onEdit}
              size="small"
            >
              {[...Array(this.state.geometryCount).keys()].map((i) => (
                <TabPane tab={`Geometry-${i}`} key={i} forceRender={true}>
                  <GeometryInput
                    index={i}
                    formRef={this.formRef}
                    ref={this.geometryRefList[i]}
                  />
                </TabPane>
              ))}
            </Tabs>
          ) : null}
        </div>
      </Form>
    );
  }

  static defaultProps = {
    title: "Setup initial structures",
    // handleSourceTypeChanged: (value) => {
    //     return value;
    // },
  };
}

export { StructureInput };
