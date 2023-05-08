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

class Rank1Tensor extends React.Component<
  PropertyInputProps,
  TensorInputState
> {
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

    for (var i = 0; i < 3; i++) {
      tensor.push({
        value: values[`${this.state.prefix}_component${i}_value`],
        index: values[`${this.state.prefix}_component${i}_index`],
      });
      console.log("tensor", `${this.state.prefix}_component${i}_value`, tensor);
    }

    return {
      name: this.props.tensorName.replace(" ", "_"),
      rank: 1,
      pointGroup: "custom",
      component: tensor,
    };
  };

  onImport = (tensorIn: TensorInputData) => {
    console.log("import from tensor ", tensorIn);

    if (this.props.formRef.current) {
      for (let j = 0; j < 3; j++) {
        const comp = tensorIn.component[j];
        if (comp.index) {
          const num = Number(comp.index) - 1;
          let value = `${this.state.prefix}_component${num}_value`;
          this.props.formRef.current.setFieldsValue({
            [value]: comp.value.trim(),
          });
        } else {
          console.warn(
            "The tensor component of rank 1 does not have index",
            comp
          );
        }
      }
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
            <Input.Group compact>
              <Form.Item name={`${this.state.prefix}_component0_value`} noStyle>
                <Input style={{ width: "33%" }} placeholder="100" />
              </Form.Item>
              <Form.Item name={`${this.state.prefix}_component1_value`} noStyle>
                <Input style={{ width: "33%" }} placeholder="100" />
              </Form.Item>
              <Form.Item name={`${this.state.prefix}_component2_value`} noStyle>
                <Input style={{ width: "33%" }} placeholder="100" />
              </Form.Item>
            </Input.Group>
          </Tooltip>
        </Form.Item>
      </>
    );
  }
}

export { Rank1Tensor };
