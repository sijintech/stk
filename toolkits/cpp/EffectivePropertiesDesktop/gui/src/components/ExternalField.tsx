import React from "react";
import { Input, Form, Select, FormInstance } from "antd";
import type {
  SystemType,
  ExternalField,
  VectorField,
  TensorRank2,
  StressTensor,
  StrainTensor,
  ElectricField,
  ConcentrationGradientField,
  MagneticField,
  TemperatureGradientField,
  PiezomagneticField,
  PiezoelectricField,
  ElasticField,
} from "./typings";

import { marginBottom } from "@mupro/typings/Constants";
const { Option } = Select;

interface ExternalFieldProps {
  type: SystemType;
}

interface ExternalFieldState {
  constrainType: "strain" | "stress";
  tensorList: ExternalTensor[];
}

interface ExternalTensor {
  title: React.ReactNode; //JSX.IntrinsicElements["span"];
  type: "vector" | "tensorRank2";
}

export const ElectricFieldTitle: ExternalTensor = {
  title: (
    <span>
      E field (V&middot;m<sup>-1</sup>)
    </span>
  ),
  type: "vector",
};
export const ConcentrationGradientTitle: ExternalTensor = {
  title: (
    <span>
      &nabla;Conc. (mol&middot;cm<sup>-4</sup>)
    </span>
  ),
  type: "vector",
};
export const MagneticFieldTitle: ExternalTensor = {
  title: (
    <span>
      H field (A&middot;m<sup>-1</sup>)
    </span>
  ),
  type: "vector",
};
export const TemperatureGradientTitle: ExternalTensor = {
  title: (
    <span>
      &nabla;Temp. (k&middot;m<sup>-1</sup>)
    </span>
  ),
  type: "vector",
};
export const StrainTitle: ExternalTensor = {
  title: <span>Strain</span>,
  type: "tensorRank2",
};
export const StressTitle: ExternalTensor = {
  title: <span>Stress (GPa)</span>,
  type: "tensorRank2",
};

class ExternalFieldInput extends React.Component<
  ExternalFieldProps,
  ExternalFieldState
> {
  formRef: React.RefObject<FormInstance>;
  state: ExternalFieldState;
  constructor(props: ExternalFieldProps) {
    super(props);
    this.formRef = React.createRef();
    this.state = {
      constrainType: "strain",
      tensorList: this.getTensorList("elastic"),
    };
  }

  componentDidUpdate(prevProps: ExternalFieldProps) {
    if (this.props.type !== prevProps.type) {
      this.setState({
        tensorList: this.getTensorList(this.state.constrainType),
      });
    }
  }

  getTensorList = (constrainType: string): ExternalTensor[] => {
    switch (this.props.type) {
      case "dielectric":
      case "electrical":
        return [ElectricFieldTitle];
      case "diffusion":
        return [ConcentrationGradientTitle];
      case "magnetic":
        return [MagneticFieldTitle];
      case "thermal":
        return [TemperatureGradientTitle];
      case "elastic":
        if (constrainType == "strain") {
          return [StrainTitle];
        } else {
          return [StressTitle];
        }
      case "piezoelectric":
        if (constrainType == "strain") {
          return [ElectricFieldTitle, StrainTitle];
        } else {
          return [ElectricFieldTitle, StressTitle];
        }
      case "piezomagnetic":
        if (constrainType === "strain") {
          return [MagneticFieldTitle, StrainTitle];
        } else {
          return [MagneticFieldTitle, StressTitle];
        }
      default:
        return [{ title: <span>empty</span>, type: "vector" }];
    }
  };

  onFinish = (): ExternalField => {
    const values = this.formRef.current!.getFieldsValue(true);
    const vector: VectorField = {
      x: values["x"],
      y: values["y"],
      z: values["z"],
    };
    const tensor: TensorRank2 = {
      tensor11: values["tensor11"],
      tensor22: values["tensor22"],
      tensor33: values["tensor33"],
      tensor23: values["tensor23"],
      tensor13: values["tensor13"],
      tensor12: values["tensor12"],
    };

    switch (this.props.type) {
      case "dielectric":
      case "electrical":
        return { electricField: vector };
      case "diffusion":
        return { concentrationGradient: vector };
      case "magnetic":
        return { magneticField: vector };
      case "thermal":
        return { temperatureGradient: vector };
      case "elastic":
        if (this.state.constrainType === "strain") {
          return { elastic: { type: "strain", strain: tensor } };
        } else {
          return { elastic: { type: "stress", stress: tensor } };
        }
      case "piezoelectric":
        if (this.state.constrainType === "strain") {
          return {
            electricField: vector,
            elastic: { type: "strain", strain: tensor },
          };
        } else {
          return {
            electricField: vector,
            elastic: { type: "stress", stress: tensor },
          };
        }
      case "piezomagnetic":
        if (this.state.constrainType === "strain") {
          return {
            magneticField: vector,
            elastic: { type: "strain", strain: tensor },
          };
        } else {
          return {
            magneticField: vector,
            elastic: { type: "stress", stress: tensor },
          };
        }
      default:
        return {
          electricField: {
            x: "empty",
            y: "empty",
            z: "empty",
          },
        };
    }
  };

  onImport = (external: ExternalField) => {
    console.log("on import in dielectric external field", external);
    let vector: VectorField | undefined;
    let tensor: TensorRank2 | undefined;
    let isStrain: boolean = true;
    switch (this.props.type) {
      case "dielectric":
      case "electrical":
        vector = (external as ElectricField).electricField;
        break;
      case "diffusion":
        console.log("on import in composition gradient field", external);
        vector = (external as ConcentrationGradientField).concentrationGradient;
        break;
      case "magnetic":
        console.log("on import in magnetic external field", external);
        vector = (external as MagneticField).magneticField;
        break;
      case "thermal":
        console.log("on import in dielectric external field", external);
        vector = (external as TemperatureGradientField).temperatureGradient;
        break;
      case "piezoelectric":
        vector = (external as PiezoelectricField).electricField;
        isStrain = (external as PiezoelectricField).elastic.type === "strain";
        if (isStrain) {
          tensor = ((external as PiezoelectricField).elastic as StrainTensor)
            .strain;
        } else {
          tensor = ((external as PiezoelectricField).elastic as StressTensor)
            .stress;
        }
        break;
      case "piezomagnetic":
        vector = (external as PiezomagneticField).magneticField;
        isStrain = (external as PiezomagneticField).elastic.type === "strain";
        if (isStrain) {
          tensor = ((external as PiezomagneticField).elastic as StrainTensor)
            .strain;
        } else {
          tensor = ((external as PiezomagneticField).elastic as StressTensor)
            .stress;
        }
        break;
      case "elastic":
        isStrain = (external as ElasticField).elastic.type === "strain";
        if (isStrain) {
          tensor = ((external as ElasticField).elastic as StrainTensor).strain;
        } else {
          tensor = ((external as ElasticField).elastic as StressTensor).stress;
        }
        break;
    }

    if (
      [
        "piezoelectric",
        "piezomagnetic",
        "thermal",
        "diffusion",
        "dielectric",
        "electrical",
        "magnetic",
      ].includes(this.props.type)
    ) {
      this.formRef.current!.setFieldsValue({
        x: vector!.x,
        y: vector!.y,
        z: vector!.z,
      });
    }

    console.log(
      "componentDidUpdate",
      isStrain,
      this.props.type,
      this.props.type in ["elastic", "piezoelectric", "piezomagnetic"]
    );
    if (
      ["elastic", "piezoelectric", "piezomagnetic"].includes(this.props.type)
    ) {
      console.log("componentDidUpdate1", isStrain, this.props.type);
      this.setState({ constrainType: isStrain ? "strain" : "stress" }, () => {
        this.formRef.current!.setFieldsValue({
          constrainType: isStrain ? "strain" : "stress",
          tensor11: tensor!.tensor11,
          tensor22: tensor!.tensor22,
          tensor33: tensor!.tensor33,
          tensor23: tensor!.tensor23,
          tensor13: tensor!.tensor13,
          tensor12: tensor!.tensor12,
        });
      });
    }
  };

  onSelectConstrainType = (value: "strain" | "stress") => {
    console.log("the constrain type changed ", value);
    this.setState({
      constrainType: value,
      tensorList: this.getTensorList(value),
    });
  };

  render() {
    const formstyle = {
      labelCol: { span: 8 },
      wrapperCol: { span: 16 },
      style: { width: "100%" },
      labelWrap: true,
    };
    const formItemStyle = {
      style: { marginBottom: marginBottom },
    };
    return (
      <Form {...formstyle} ref={this.formRef}>
        <>
          {["elastic", "piezoelectric", "piezomagnetic"].includes(
            this.props.type
          ) ? (
            <Form.Item name="constrainType" label="Constraint Type">
              <Select
                placeholder="Select the constrain type"
                onChange={(value: "stress" | "strain") => {
                  this.onSelectConstrainType(value);
                }}
              >
                <Option value={"stress"}>Stress</Option>
                <Option value={"strain"}>Strain</Option>
              </Select>
            </Form.Item>
          ) : null}
        </>
        <>
          {this.state.tensorList.map((tensor: ExternalTensor, i: number) => {
            if (tensor.type == "vector") {
              return (
                <Form.Item key={i} label={tensor.title} {...formItemStyle}>
                  <Input.Group compact>
                    <Form.Item name="x" noStyle rules={[{ required: true }]}>
                      <Input style={{ width: "33.3%" }} placeholder="0" />
                    </Form.Item>
                    <Form.Item name="y" noStyle rules={[{ required: true }]}>
                      <Input style={{ width: "33.3%" }} placeholder="0" />
                    </Form.Item>
                    <Form.Item name="z" noStyle rules={[{ required: true }]}>
                      <Input style={{ width: "33.3%" }} placeholder="1e6" />
                    </Form.Item>
                  </Input.Group>
                </Form.Item>
              );
            } else {
              return (
                <Form.Item key={i} label={tensor.title} {...formItemStyle}>
                  <Input.Group compact>
                    <Form.Item
                      name="tensor11"
                      noStyle
                      rules={[{ required: true }]}
                    >
                      <Input style={{ width: "16.9%" }} placeholder="0" />
                    </Form.Item>
                    <Form.Item
                      name="tensor22"
                      noStyle
                      rules={[{ required: true }]}
                    >
                      <Input style={{ width: "16.9%" }} placeholder="0" />
                    </Form.Item>
                    <Form.Item
                      name="tensor33"
                      noStyle
                      rules={[{ required: true }]}
                    >
                      <Input style={{ width: "16.9%" }} placeholder="0" />
                    </Form.Item>
                    <Form.Item
                      name="tensor23"
                      noStyle
                      rules={[{ required: true }]}
                    >
                      <Input style={{ width: "16.9%" }} placeholder="0" />
                    </Form.Item>
                    <Form.Item
                      name="tensor13"
                      noStyle
                      rules={[{ required: true }]}
                    >
                      <Input style={{ width: "16.9%" }} placeholder="0" />
                    </Form.Item>
                    <Form.Item
                      name="tensor12"
                      noStyle
                      rules={[{ required: true }]}
                    >
                      <Input style={{ width: "16.9%" }} placeholder="0" />
                    </Form.Item>
                  </Input.Group>
                </Form.Item>
              );
            }
          })}
        </>
      </Form>
    );
  }
}

export { ExternalFieldInput };
