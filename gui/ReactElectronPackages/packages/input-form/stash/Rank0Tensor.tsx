import React from "react";
import { Input, Form, Tooltip, FormInstance } from "antd";
import type {
  TensorInputData,
  TensorComponentData,
} from "@mupro/typings/TensorInput";
import { defaultTensorInput } from "@mupro/typings/TensorInput";
import { marginBottom } from "@mupro/typings/Constants";

import type { PropertyInputProps } from ".";

interface TensorInputState {
  prefix: string;
}

class Rank0Tensor extends React.Component<
  PropertyInputProps,
  TensorInputState
> {
  // indexRefList: [React.RefObject<FormInstance>];
  state: TensorInputState;

  constructor(props: PropertyInputProps) {
    super(props);
    this.state = {
      prefix: `phase${this.props.phaseIndex}_${this.props.tensorName.replace(
        " ",
        "_"
      )}`,
    };
  }

  onFinish = (): TensorInputData => {
    if (!this.props.formRef.current) {
      return defaultTensorInput;
    }
    var values = this.props.formRef.current.getFieldsValue(true);
    var tensor: TensorComponentData[] = [];
    var pg = "custom";

    tensor.push({
      value: values[`${this.state.prefix}_component0_value`],
    });

    return {
      name: this.props.tensorName.replace(" ", "_"),
      rank: 0,
      pointGroup: pg,
      component: tensor,
    };
  };

  onImport = (tensorIn: TensorInputData) => {
    console.log("import from tensor ", tensorIn);
    if (this.props.formRef.current) {
      this.props.formRef.current.setFieldsValue({
        [`${this.state.prefix}_component0_value`]:
          tensorIn.component[0].value.trim(),
      });
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
        <Form.Item label={this.props.tensorName} {...formItemStyle}>
          <Tooltip
            title={`One component for ${this.props.tensorName}`}
            placement="bottom"
          >
            <Form.Item name={`${this.state.prefix}_component0_value`} noStyle>
              <Input style={{ width: "33%" }} placeholder="100" />
            </Form.Item>
          </Tooltip>
        </Form.Item>
      </>
    );
  }
}

export { Rank0Tensor };
