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

class Rank1Tensor extends TensorBase {
  // indexRefList: [React.RefObject<FormInstance>];

  constructor(props: PropertyInputProps) {
    super(props);

    this.state = {
      prefix: `phase${this.props.phaseIndex}_${this.props.id}`,
      rank: 1,
      symmetry: "custom",
      disabled: defaultDisable,
      tensor: {
        "1": "1",
        "2": "2",
        "3": "3",
      },
    };
  }

  render() {
    const formItemStyle = {
      style: { marginBottom: marginBottom },
    };
    const tensorStyle = {
      labelCol: { span: 0 },
      wrapperCol: { span: 24 },
      style: {
        width: "100%",
        textAlign: "right" as const,
        marginBottom: "0px",
      },
    };
    const componentStyle = {
      style: { width: "33.3%" },
    };
    return (
      <>
        <h4>{this.props.tensorName}</h4>

        <Form.Item {...tensorStyle}>
          <Input.Group compact>
            <Form.Item name={`${this.state.prefix}_1`} noStyle>
              <Input
                {...componentStyle}
                onChange={this.handleComponentChange}
                placeholder={this.state.tensor["1"]}
              />
            </Form.Item>
            <Form.Item name={`${this.state.prefix}_2`} noStyle>
              <Input
                {...componentStyle}
                onChange={this.handleComponentChange}
                placeholder={this.state.tensor["2"]}
                disabled={this.state.disabled["2"]}
              />
            </Form.Item>
            <Form.Item name={`${this.state.prefix}_3`} noStyle>
              <Input
                {...componentStyle}
                onChange={this.handleComponentChange}
                placeholder={this.state.tensor["3"]}
                disabled={this.state.disabled["3"]}
              />
            </Form.Item>
          </Input.Group>
        </Form.Item>
      </>
    );
  }
}

export { Rank1Tensor };
