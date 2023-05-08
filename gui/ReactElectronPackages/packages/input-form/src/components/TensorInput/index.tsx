import React from "react";
import { Input, Form, Tooltip, Tabs, Select, FormInstance } from "antd";
import type {
  TensorInputData,
  TensorComponentData,
  TensorType,
} from "@mupro/typings/TensorInput";
import { defaultTensorInput } from "@mupro/typings/TensorInput";
import { marginBottom } from "@mupro/typings/Constants";
import { Rank2Tensor } from "./Rank2Tensor";
import { Rank0Tensor } from "./Rank0Tensor";
import { Rank1Tensor } from "./Rank1Tensor";
import { PiezoelectricTensor } from "./Piezoelectric";
import { PiezomagneticTensor } from "./Piezomagnetic";
import { StiffnessTensor } from "./Stiffness";
// import { Rank1Tensor } from "./Rank1Tensor";
// import {log } from "log";
const { Option } = Select;
const { TabPane } = Tabs;

interface TensorInputProps {
  phaseIndex: string;
  tensor: TensorType;
  // id: string;
  // rank: number;
}

interface PropertyInputProps {
  phaseIndex: string;
  tensorName: string | React.ReactNode;
  formRef: React.RefObject<FormInstance>;
  id: string;
}

interface TensorOption {
  value: string;
  disabled: boolean;
}

const defaultOption: TensorOption = { value: "", disabled: false };

// type TensorOptions=TensorOption[];
type TensorOptions = string[];

interface Dictionary<T> {
  [Key: string]: T;
}
interface TensorInputState {}

class TensorInput extends React.Component<TensorInputProps, TensorInputState> {
  formRef: React.RefObject<FormInstance>;
  // indexRefList: [React.RefObject<FormInstance>];
  // state: TensorInputState;
  tensorRef: React.RefObject<
    Rank2Tensor | PiezoelectricTensor | PiezomagneticTensor | StiffnessTensor
    // | Rank0Tensor
    // | Rank1Tensor
  >;

  constructor(props: TensorInputProps) {
    super(props);
    this.formRef = React.createRef();
    this.tensorRef = React.createRef();
  }

  onFinish = (): TensorInputData => {
    if (!this.formRef.current || !this.tensorRef.current) {
      return defaultTensorInput;
    }
    let values = this.formRef.current.getFieldsValue(true);
    console.log("The tensor onFinish, ", values);
    return this.tensorRef.current.onFinish(values);
  };

  onImport = (tensorIn: TensorInputData) => {
    console.log(
      "TensorInput::onImport",
      tensorIn,
      this.formRef,
      this.tensorRef
    );
    if (this.formRef.current !== null && this.tensorRef.current !== null) {
      console.log("not null");
      this.tensorRef.current.onImport(tensorIn);
    }
  };

  render() {
    const formStyle = {
      labelCol: { span: 8 },
      wrapperCol: { span: 16 },
      style: { width: "100%" },
    };
    return (
      <Form {...formStyle} ref={this.formRef}>
        {this.props.tensor.rank === 0 ? (
          <Rank0Tensor
            phaseIndex={this.props.phaseIndex}
            tensorName={this.props.tensor.name}
            id={this.props.tensor.id}
            formRef={this.formRef}
            ref={this.tensorRef as React.RefObject<Rank2Tensor>}
          />
        ) : null}
        {this.props.tensor.rank === 1 ? (
          <Rank1Tensor
            phaseIndex={this.props.phaseIndex}
            tensorName={this.props.tensor.name}
            id={this.props.tensor.id}
            formRef={this.formRef}
            ref={this.tensorRef as React.RefObject<Rank1Tensor>}
          />
        ) : null}
        {this.props.tensor.rank === 2 ? (
          <Rank2Tensor
            phaseIndex={this.props.phaseIndex}
            tensorName={this.props.tensor.name}
            id={this.props.tensor.id}
            formRef={this.formRef}
            ref={this.tensorRef as React.RefObject<Rank2Tensor>}
          />
        ) : null}

        {this.props.tensor.id === "stiffness" ? (
          <StiffnessTensor
            phaseIndex={this.props.phaseIndex}
            tensorName={this.props.tensor.name}
            id={this.props.tensor.id}
            formRef={this.formRef}
            ref={this.tensorRef as React.RefObject<StiffnessTensor>}
          />
        ) : null}

        {this.props.tensor.id === "piezoelectric" ? (
          <PiezoelectricTensor
            phaseIndex={this.props.phaseIndex}
            tensorName={this.props.tensor.name}
            formRef={this.formRef}
            id={this.props.tensor.id}
            ref={this.tensorRef as React.RefObject<PiezoelectricTensor>}
          />
        ) : null}

        {this.props.tensor.id === "piezomagnetic" ? (
          <PiezomagneticTensor
            phaseIndex={this.props.phaseIndex}
            tensorName={this.props.tensor.name}
            formRef={this.formRef}
            id={this.props.tensor.id}
            ref={this.tensorRef as React.RefObject<PiezomagneticTensor>}
          />
        ) : null}
      </Form>
    );
  }
}

export { TensorInput };
export type { PropertyInputProps };
