import React from "react";
import { Input, Form, Tooltip, Select, FormInstance } from "antd";
import type {
  TensorInputData,
  TensorComponentData,
} from "@mupro/typings/TensorInput";
import { defaultTensorInput } from "@mupro/typings/TensorInput";
import { marginBottom } from "@mupro/typings/Constants";
// import {log } from "log";
import type { PropertyInputProps } from ".";
import { identity } from "mathjs";
import { TensorBase, disabledDict, tensorDict } from "./TensorBase";

const { Option } = Select;

const defaultDisable: disabledDict = {
  "1": false,
  "2": false,
  "3": false,
};

class Rank0Tensor extends TensorBase {
  // indexRefList: [React.RefObject<FormInstance>];

  constructor(props: PropertyInputProps) {
    super(props);

    this.state = {
      prefix: `phase${this.props.phaseIndex}_${this.props.id}`,
      rank: 0,
      symmetry: "custom",
      disabled: defaultDisable,
      tensor: {
        "1": "0",
      },
    };
  }

  render() {
    const formItemStyle = {
      style: { marginBottom: marginBottom },
    };
    const tensorStyle = {
      labelCol: { span: 10 },
      wrapperCol: { span: 14 },
      style: {
        width: "100%",
        textAlign: "left" as const,
        marginBottom: "0px",
      },
    };
    const componentStyle = {
      style: { width: "50%" },
    };
    const title = (
      <span style={{ fontWeight: 500 }}>{this.props.tensorName}</span>
    );
    return (
      <>
        <Form.Item label={title} {...tensorStyle}>
          <Input.Group compact>
            <Form.Item name={`${this.state.prefix}_1`} noStyle>
              <Input
                {...componentStyle}
                onChange={this.handleComponentChange}
                placeholder={this.state.tensor["1"]}
              />
            </Form.Item>
          </Input.Group>
        </Form.Item>
      </>
    );
  }
}

export { Rank0Tensor };
