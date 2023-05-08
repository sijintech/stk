import React from "react";
import { Form, Tooltip, Select, FormInstance } from "antd";
import { SlabInput } from "./slabInput";
import { EllipsoidInput } from "./ellipsoidInput";
import { EllipsoidShellInput } from "./ellipsoidShellInput";
import { EllipsoidRandomInput } from "./ellipsoidRandomInput";
import { EllipsoidRandomScaleInput } from "./ellipsoidRandomScaleInput";
import { EllipsoidShellRandomInput } from "./ellipsoidShellRandomInput";
import { EllipsoidShellRandomScaleInput } from "./ellipsoidShellRandomScaleInput";

import type {
  GeometryInputData,
  SlabInputData,
  EllipsoidInputData,
  EllipsoidRandomInputData,
  EllipsoidRandomScaleInputData,
  EllipsoidShellInputData,
  EllipsoidShellRandomInputData,
  EllipsoidShellRandomScaleInputData,
} from "@mupro/typings/GeometryInput";

const { Option } = Select;

type GeometryType =
  | "empty"
  | "slab"
  | "ellipsoid"
  | "ellipsoid_shell"
  | "ellipsoid_random"
  | "ellipsoid_random_scale"
  | "ellipsoid_shell_random"
  | "ellipsoid_shell_random_scale";

interface GeometryInputState {
  geometryType: GeometryType;
}

interface GeometryInputProps {
  index: number;
  formRef: React.RefObject<FormInstance>;
}

type Geometry =
  | SlabInput
  | EllipsoidInput
  | EllipsoidShellInput
  | EllipsoidRandomInput
  | EllipsoidRandomScaleInput
  | EllipsoidShellRandomInput
  | EllipsoidShellRandomScaleInput;

class GeometryInput extends React.Component<
  GeometryInputProps,
  GeometryInputState
> {
  state: GeometryInputState;
  // geometryFormRef: React.RefObject<Geometry>;
  slabFormRef: React.RefObject<SlabInput>;
  ellipsoidFormRef: React.RefObject<EllipsoidInput>;
  ellipsoidShellFormRef: React.RefObject<EllipsoidShellInput>;
  ellipsoidRandomFormRef: React.RefObject<EllipsoidRandomInput>;
  ellipsoidRandomScaleFormRef: React.RefObject<EllipsoidRandomScaleInput>;
  ellipsoidShellRandomFormRef: React.RefObject<EllipsoidShellRandomInput>;
  ellipsoidShellRandomScaleFormRef: React.RefObject<EllipsoidShellRandomScaleInput>;
  // geometryFormRef: React.RefObject<SlabInput> | React.RefObject<EllipsoidInput> |React.RefObject<EllipsoidShellInput>|React.RefObject<EllipsoidRandomInput>|React.RefObject<EllipsoidRandomScaleInput>|React.RefObject<EllipsoidShellRandomInput>|React.RefObject<EllipsoidShellRandomScaleInput>;

  constructor(props: GeometryInputProps) {
    super(props);
    this.slabFormRef = React.createRef();
    this.ellipsoidFormRef = React.createRef();
    this.ellipsoidShellFormRef = React.createRef();
    this.ellipsoidRandomFormRef = React.createRef();
    this.ellipsoidRandomScaleFormRef = React.createRef();
    this.ellipsoidShellRandomFormRef = React.createRef();
    this.ellipsoidShellRandomScaleFormRef = React.createRef();
    this.state = {
      geometryType: "empty",
      // geometryRef: null,
    };
  }

  getCurrentGeometryRef = () => {
    switch (this.state.geometryType) {
      case "slab":
        return this.slabFormRef;
      case "ellipsoid":
        return this.ellipsoidFormRef;
      case "ellipsoid_shell":
        return this.ellipsoidShellFormRef;
      case "ellipsoid_random":
        return this.ellipsoidRandomFormRef;
      case "ellipsoid_random_scale":
        return this.ellipsoidRandomScaleFormRef;
      case "ellipsoid_shell_random":
        return this.ellipsoidShellRandomFormRef;
      case "ellipsoid_shell_random_scale":
        return this.ellipsoidShellRandomScaleFormRef;
      default:
        return null;
    }
  };

  onImport = (geometry: GeometryInputData) => {
    console.log("GeometryInput::onImport::geometry", geometry);
    if (!this.props.formRef.current) return;
    const geometryType: GeometryType = geometry.type.trim() as GeometryType;
    this.setState(
      {
        geometryType: geometryType,
      },
      () => {
        this.props.formRef.current!.setFieldsValue({
          [`geometry${this.props.index}_type`]: this.state.geometryType,
        });
        console.log(this.props.index);
        console.log(this.getCurrentGeometryRef());

        switch (geometry.type) {
          case "slab":
            geometry = geometry;
            this.slabFormRef.current?.onImport(geometry as SlabInputData);
            break;
          case "ellipsoid":
            this.ellipsoidFormRef.current?.onImport(
              geometry as EllipsoidInputData
            );
            break;
          case "ellipsoid_shell":
            this.ellipsoidShellFormRef.current?.onImport(
              geometry as EllipsoidShellInputData
            );
            break;
          case "ellipsoid_random":
            this.ellipsoidRandomFormRef.current?.onImport(
              geometry as EllipsoidRandomInputData
            );
            break;
          case "ellipsoid_random_scale":
            this.ellipsoidRandomScaleFormRef.current?.onImport(
              geometry as EllipsoidRandomScaleInputData
            );
            break;
          case "ellipsoid_shell_random":
            this.ellipsoidShellRandomFormRef.current?.onImport(
              geometry as EllipsoidShellRandomInputData
            );
            break;
          case "ellipsoid_shell_random_scale":
            this.ellipsoidShellRandomScaleFormRef.current?.onImport(
              geometry as EllipsoidShellRandomScaleInputData
            );
            break;
        }
      }
    );
  };

  onFinish = (values: any): GeometryInputData | undefined => {
    if (this.getCurrentGeometryRef()) {
      return this.getCurrentGeometryRef()!.current?.onFinish(
        values
      ) as GeometryInputData;
    } else {
      return undefined;
    }
  };

  onSelectGeometryType = (value: GeometryType) => {
    this.setState({ geometryType: value });
    console.log("geometry type changed ", value, this.state);
  };

  // onEdit = (targetKey, action) => {
  //   this[action](targetKey);
  // };

  getGeometry(geometryType: GeometryType) {}
  render() {
    return (
      <div>
        <>
          <Form.Item label="Geometry type" colon={false}>
            <Tooltip
              title="Check to use a microstructure.xml for phase distribution, 
        uncheck to define the structure directly inside the input.xml"
              placement="bottomLeft"
            >
              <Form.Item
                name={`geometry${this.props.index}_type`}
                // colon='false'
                noStyle
              >
                {/* <Checkbox onChange={this.fromFileChanged} checked={this.props.simConfig.fromFile}> Using structure file</Checkbox> */}
                <Select
                  placeholder="Choose geometry"
                  onChange={(value) => this.onSelectGeometryType(value)}
                >
                  <Option value={"slab"}>Slab</Option>
                  <Option value={"ellipsoid"}>Ellipsoid</Option>
                  <Option value={"ellipsoid_random"}>Random Ellipsoid</Option>
                  <Option value={"ellipsoid_random_scale"}>
                    Random Scale Ellipsoid
                  </Option>
                  <Option value={"ellipsoid_shell"}>Ellipsoid Shell</Option>
                  <Option value={"ellipsoid_shell_random"}>
                    Random Ellipsoid Shell
                  </Option>
                  <Option value={"ellipsoid_shell_random_scale"}>
                    Random Scale Ellipsoid Shell
                  </Option>
                </Select>
              </Form.Item>
            </Tooltip>
          </Form.Item>
          {(() => {
            switch (this.state.geometryType) {
              case "slab":
                console.log("chose slab");
                return (
                  <SlabInput
                    ref={this.slabFormRef}
                    index={this.props.index}
                    formRef={this.props.formRef}
                  />
                );
              case "ellipsoid":
                return (
                  <EllipsoidInput
                    index={this.props.index}
                    ref={this.ellipsoidFormRef}
                    formRef={this.props.formRef}
                  />
                );
              case "ellipsoid_random":
                return (
                  <EllipsoidRandomInput
                    index={this.props.index}
                    ref={this.ellipsoidRandomFormRef}
                    formRef={this.props.formRef}
                  />
                );
              case "ellipsoid_random_scale":
                return (
                  <EllipsoidRandomScaleInput
                    index={this.props.index}
                    ref={
                      this
                        .ellipsoidRandomScaleFormRef as React.RefObject<EllipsoidRandomScaleInput>
                    }
                    formRef={this.props.formRef}
                  />
                );
              case "ellipsoid_shell":
                return (
                  <EllipsoidShellInput
                    index={this.props.index}
                    ref={
                      this
                        .ellipsoidShellFormRef as React.RefObject<EllipsoidShellInput>
                    }
                    formRef={this.props.formRef}
                  />
                );
              case "ellipsoid_shell_random":
                return (
                  <EllipsoidShellRandomInput
                    index={this.props.index}
                    ref={
                      this
                        .ellipsoidShellRandomFormRef as React.RefObject<EllipsoidShellRandomInput>
                    }
                    formRef={this.props.formRef}
                  />
                );
              case "ellipsoid_shell_random_scale":
                return (
                  <EllipsoidShellRandomScaleInput
                    index={this.props.index}
                    ref={
                      this
                        .ellipsoidShellRandomScaleFormRef as React.RefObject<EllipsoidShellRandomScaleInput>
                    }
                    formRef={this.props.formRef}
                  />
                );
              default:
                return null;
            }
          })()}
        </>
      </div>
    );
  }
}

export { GeometryInput };
export type { GeometryInputProps };
