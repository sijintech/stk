import React from "react";
import { Input, Form, Divider, FormInstance } from "antd";
import { TensorInput } from "./TensorInput";
import { defaultTensorInput } from "@mupro/typings/TensorInput";
import type { TensorInputData, TensorType } from "@mupro/typings/TensorInput";
import type { PhaseInputData } from "@mupro/typings/PhaseInput";
import { defaultPhaseInput } from "@mupro/typings/PhaseInput";
import { marginBottom } from "@mupro/typings/Constants";

interface PhaseProps {
  phaseIndex: string;
  // tensorList: { name: string | React.ReactNode; rank: number }[];
  tensorList: TensorType[];
}

class PhaseInput extends React.Component<PhaseProps, {}> {
  formRef: React.RefObject<FormInstance>;
  tensorRefList: React.RefObject<TensorInput>[];

  constructor(props: PhaseProps) {
    super(props);
    console.log(
      "construct phase ",
      this.props.phaseIndex,
      this.props.tensorList
    );
    this.formRef = React.createRef();
    this.tensorRefList = [React.createRef<TensorInput>()];
    for (let j = 0; j < this.props.tensorList.length - 1; j++) {
      this.tensorRefList.push(React.createRef());
    }
    this.state = {
      activeKey: 0,
    };
  }

  onFinish = (): PhaseInputData => {
    if (this.formRef.current) {
      let values = this.formRef.current.getFieldsValue(true);
      console.log("on finish from the phase input of ", this.props.phaseIndex);

      let tensorList: TensorInputData[] = [];
      for (let j = 0; j < this.props.tensorList.length; j++) {
        tensorList.push(defaultTensorInput);
        tensorList[j] = this.tensorRefList[j].current!.onFinish();
        // this.tensorRefList[j].current
      }
      if (
        this.props.phaseIndex === "ref" ||
        this.props.phaseIndex === "breakdown"
      ) {
        return {
          tensor: tensorList,
        };
      } else {
        return {
          label: values[`phase${this.props.phaseIndex}_label`],
          tensor: tensorList,
        };
      }
    } else {
      return defaultPhaseInput;
    }
  };

  onSelectTensorSymmetry = (values: any) => {
    console.log("select tensor symmetry ", values);
  };

  onImport = (phaseIn: PhaseInputData) => {
    console.log(
      "import in the phase",
      this.props.phaseIndex,
      phaseIn,
      this.formRef
    );

    if (this.formRef.current) {
      if (
        // this.props.phaseIndex !== "ref" &&
        // this.props.phaseIndex !== "breakdown"
        phaseIn.label
      ) {
        // for (let i = 0; i < phaseIn.length; i++) {
        // const element = phaseIn[i];
        this.formRef.current.setFieldsValue({
          [`phase${this.props.phaseIndex}_label`]: phaseIn.label.trim(),
        });
        // }
      }
    }

    console.log(
      "tensor list",
      this.props.tensorList.length,
      this.tensorRefList
    );
    for (let j = 0; j < this.props.tensorList.length; j++) {
      console.log(j, this.props.phaseIndex, phaseIn, this.tensorRefList[j]);
      this.tensorRefList[j].current!.onImport(phaseIn.tensor[j]);
    }
  };
  render() {
    const formStyle = {
      labelCol: { span: 8 },
      wrapperCol: { span: 16 },
      style: { width: "100%" },
    };
    const formItemStyle = {
      style: { marginBottom: marginBottom },
    };
    return (
      <>
        <Form {...formStyle} ref={this.formRef}>
          {this.props.phaseIndex === "ref" ||
          this.props.phaseIndex === "breakdown" ? null : (
            <Form.Item
              label="Label"
              name={`phase${this.props.phaseIndex}_label`}
              {...formItemStyle}
            >
              <Input style={{ width: "33%" }} placeholder="0" />
            </Form.Item>
          )}
        </Form>
        {[...Array(this.props.tensorList.length).keys()].map((j) => (
          <div key={j.toString()}>
            <TensorInput
              ref={this.tensorRefList[j]}
              phaseIndex={this.props.phaseIndex}
              tensor={this.props.tensorList[j]}
            />
            <Divider
              style={{
                marginTop: marginBottom,
                marginBottom: marginBottom,
              }}
            />
          </div>
        ))}
      </>
    );
  }
}

export { PhaseInput };
