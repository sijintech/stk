import React from "react";
import { Input, Form, Tooltip, Select, FormInstance } from "antd";
import type {
  TensorInputData,
  TensorComponentData,
} from "@mupro/typings/TensorInput";
import { defaultTensorInput } from "@mupro/typings/TensorInput";
import { marginBottom } from "@mupro/typings/Constants";
import { evaluate } from "mathjs";
import type { PropertyInputProps } from ".";
// import {log } from "log";
const { Option } = Select;

import { TensorBase, disabledDict, tensorDict } from "./TensorBase";

const defaultDisable: disabledDict = {
  "11": false,
  "12": false,
  "13": false,
  "14": false,
  "15": false,
  "16": false,
  "21": false,
  "22": false,
  "23": false,
  "24": false,
  "25": false,
  "26": false,
  "31": false,
  "32": false,
  "33": false,
  "34": false,
  "35": false,
  "36": false,
};

class PiezoelectricTensor extends TensorBase {
  // indexRefList: [React.RefObject<FormInstance>];

  constructor(props: PropertyInputProps) {
    super(props);

    this.state = {
      prefix: `phase${this.props.phaseIndex}_${this.props.id}`,
      rank: 3,
      symmetry: "custom",
      disabled: defaultDisable,
      tensor: {
        "11": "11",
        "12": "12",
        "13": "13",
        "14": "14",
        "15": "15",
        "16": "16",
        "21": "21",
        "22": "22",
        "23": "23",
        "24": "24",
        "25": "25",
        "26": "26",
        "31": "31",
        "32": "32",
        "33": "33",
        "34": "34",
        "35": "35",
        "36": "36",
      },
    };
  }

  getSymmetryConstraint = (
    sym: string
  ): [zeros: string[], fields: Record<string, string>] => {
    switch (sym) {
      case "zero":
        return [
          ["21","22","23","24","25","26", "11","12","13","14","15","16", "31","32","33","34","35","36"], // prettier-ignore
          {},
        ];
      case "1":
        return [[], {}];
      case "2":
        return [
          ["11", "12", "13", "15", "24", "26", "31", "32", "33", "35"],
          {},
        ];
      case "m":
        return [
          ["14", "16", "21","22","23","25", "34","36"], // prettier-ignore
          {},
        ];
      case "mm2":
        return [
          ["11", "12", "13", "14","16", "21","22","23","25", "26", "34", "35", "36"], // prettier-ignore
          {},
        ];
      case "222":
        return [
          ["11", "12", "13", "15","16", "21","22","23","24", "26","31","32","33", "34", "35"], // prettier-ignore
          {},
        ];
      case "3":
        return [
          ["13", "23", "34","35", "36"], // prettier-ignore
          { "12":"-@11","21": "-@22", "16": "-2*@22","24":"@15","25":"-@14","26":"-2*@11","32":"@31"}, // prettier-ignore
        ];
      case "32":
        return [
          ["13","15","16", "21","22","23","24","31","32","33", "34","35", "36"], // prettier-ignore
          { "12": "-@11", "25": "-@14" ,"26":"-2*@11"}, // prettier-ignore
        ];
      case "3m":
        return [
          ["23","25","26", "11","12","13","14", "34","35", "36"], // prettier-ignore
          {"21":"-@22","16":"-2*@22",  "24": "@15" ,"32":"@31"}, // prettier-ignore
        ];
      case "4":
        return [
          ["21","22","23","26", "11","12","13","16", "34","35", "36"], // prettier-ignore
          { "25": "-@14", "24": "@15" ,"32":"@31"}, // prettier-ignore
        ];
      case "bar4":
        return [
          ["21","22","23","26", "11","12","13","16", "33","34","35"], // prettier-ignore
          { "25": "@14", "24": "-@15" ,"32":"-@31"}, // prettier-ignore
        ];
      case "4mm":
        return [
          ["21","22","23","25","26", "11","12","13","14","16", "34","35", "36"], // prettier-ignore
          { "24": "@15" ,"32":"@31"}, // prettier-ignore
        ];
      case "422":
        return [
          ["21","22","23","24","26", "11","12","13","15","16", "31","32","33","34","35", "36"], // prettier-ignore
          { "25": "-@14"}, // prettier-ignore
        ];
      case "bar42m":
        return [
          ["21","22","23","24","26", "11","12","13","15","16", "31","32","33","34","35"], // prettier-ignore
          { "25": "@14"}, // prettier-ignore
        ];
      case "bar6":
        return [
          ["23","24","25", "13","14","15", "31","32","33","34","35","36"], // prettier-ignore
          { "12": "-@11","21":"-@22","16":"-2*@22","26":"-2*@11"}, // prettier-ignore
        ];
      case "bar6m2":
        return [
          ["23","24","25","26", "11","12","13","14","15", "31","32","33","34","35","36"], // prettier-ignore
          { "21":"-@22","16":"-2*@22"}, // prettier-ignore
        ];
      case "bar43m":
        return [
          ["21","22","23","24","26", "11","12","13","15","16", "31","32","33","34","35"], // prettier-ignore
          { "25":"@14","36":"@14"}, // prettier-ignore
        ];
      default:
        return [[], {}];
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
    const componentStyle = {
      style: { width: "16.7%" },
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
    return (
      <>
        <h4>{this.props.tensorName}</h4>
        <Form.Item
          label="Symmetry"
          name={`${this.state.prefix}_symmetry`}
          {...formItemStyle}
        >
          <Select
            placeholder="Select the tensor symmetry"
            onChange={this.onSelectTensorSymmetry}
          >
            <Option value={"zero"}>Zero(Other symmetry)</Option>
            <Option value={"1"}>1</Option>
            <Option value={"2"}>2</Option>
            <Option value={"m"}>m </Option>
            <Option value={"mm2"}>mm2</Option>
            <Option value={"222"}>222</Option>
            <Option value={"3"}>3</Option>
            <Option value={"32"}>32</Option>
            <Option value={"3m"}>3m</Option>
            <Option value={"4"}>4,6,&infin;</Option>
            <Option value={"bar4"}>
              <span style={{ textDecoration: "overline" }}>4</span>
            </Option>
            <Option value={"4mm"}>4mm,6mm,&infin;m</Option>
            <Option value={"422"}>422,622,&infin;2</Option>
            <Option value={"bar42m"}>
              <span style={{ textDecoration: "overline" }}>4</span>2m
            </Option>
            <Option value={"bar6"}>
              <span style={{ textDecoration: "overline" }}>6</span>
            </Option>
            <Option value={"bar6m2"}>
              <span style={{ textDecoration: "overline" }}>6</span>m2
            </Option>
            <Option value={"bar43m"}>
              <span style={{ textDecoration: "overline" }}>4</span>3m, 23
            </Option>
          </Select>
        </Form.Item>

        <Form.Item {...tensorStyle}>
          <Input.Group compact>
            <Form.Item name={`${this.state.prefix}_11`} noStyle>
              <Input
                {...componentStyle}
                onChange={this.handleComponentChange}
                placeholder={this.state.tensor["11"]}
                disabled={this.state.disabled["11"]}
              />
            </Form.Item>
            <Form.Item name={`${this.state.prefix}_12`} noStyle>
              <Input
                {...componentStyle}
                onChange={this.handleComponentChange}
                placeholder={this.state.tensor["12"]}
                disabled={this.state.disabled["12"]}
              />
            </Form.Item>
            <Form.Item name={`${this.state.prefix}_13`} noStyle>
              <Input
                {...componentStyle}
                onChange={this.handleComponentChange}
                placeholder={this.state.tensor["13"]}
                disabled={this.state.disabled["13"]}
              />
            </Form.Item>
            <Form.Item name={`${this.state.prefix}_14`} noStyle>
              <Input
                {...componentStyle}
                onChange={this.handleComponentChange}
                placeholder={this.state.tensor["14"]}
                disabled={this.state.disabled["14"]}
              />
            </Form.Item>
            <Form.Item name={`${this.state.prefix}_15`} noStyle>
              <Input
                {...componentStyle}
                onChange={this.handleComponentChange}
                placeholder={this.state.tensor["15"]}
                disabled={this.state.disabled["15"]}
              />
            </Form.Item>
            <Form.Item name={`${this.state.prefix}_16`} noStyle>
              <Input
                {...componentStyle}
                onChange={this.handleComponentChange}
                placeholder={this.state.tensor["16"]}
                disabled={this.state.disabled["16"]}
              />
            </Form.Item>
          </Input.Group>
        </Form.Item>

        <Form.Item {...tensorStyle}>
          <Input.Group compact>
            <Form.Item name={`${this.state.prefix}_21`} noStyle>
              <Input
                {...componentStyle}
                onChange={this.handleComponentChange}
                placeholder={this.state.tensor["21"]}
                disabled={this.state.disabled["21"]}
              />
            </Form.Item>
            <Form.Item name={`${this.state.prefix}_22`} noStyle>
              <Input
                {...componentStyle}
                onChange={this.handleComponentChange}
                placeholder={this.state.tensor["22"]}
                disabled={this.state.disabled["22"]}
              />
            </Form.Item>
            <Form.Item name={`${this.state.prefix}_23`} noStyle>
              <Input
                {...componentStyle}
                onChange={this.handleComponentChange}
                placeholder={this.state.tensor["23"]}
                disabled={this.state.disabled["23"]}
              />
            </Form.Item>
            <Form.Item name={`${this.state.prefix}_24`} noStyle>
              <Input
                {...componentStyle}
                onChange={this.handleComponentChange}
                placeholder={this.state.tensor["24"]}
                disabled={this.state.disabled["24"]}
              />
            </Form.Item>
            <Form.Item name={`${this.state.prefix}_25`} noStyle>
              <Input
                {...componentStyle}
                onChange={this.handleComponentChange}
                placeholder={this.state.tensor["25"]}
                disabled={this.state.disabled["25"]}
              />
            </Form.Item>
            <Form.Item name={`${this.state.prefix}_26`} noStyle>
              <Input
                {...componentStyle}
                onChange={this.handleComponentChange}
                placeholder={this.state.tensor["26"]}
                disabled={this.state.disabled["26"]}
              />
            </Form.Item>
          </Input.Group>
        </Form.Item>

        <Form.Item {...tensorStyle}>
          <Input.Group compact>
            <Form.Item name={`${this.state.prefix}_31`} noStyle>
              <Input
                {...componentStyle}
                onChange={this.handleComponentChange}
                placeholder={this.state.tensor["31"]}
                disabled={this.state.disabled["31"]}
              />
            </Form.Item>
            <Form.Item name={`${this.state.prefix}_32`} noStyle>
              <Input
                {...componentStyle}
                onChange={this.handleComponentChange}
                placeholder={this.state.tensor["32"]}
                disabled={this.state.disabled["32"]}
              />
            </Form.Item>
            <Form.Item name={`${this.state.prefix}_33`} noStyle>
              <Input
                {...componentStyle}
                onChange={this.handleComponentChange}
                placeholder={this.state.tensor["33"]}
                disabled={this.state.disabled["33"]}
              />
            </Form.Item>
            <Form.Item name={`${this.state.prefix}_34`} noStyle>
              <Input
                {...componentStyle}
                onChange={this.handleComponentChange}
                placeholder={this.state.tensor["34"]}
                disabled={this.state.disabled["34"]}
              />
            </Form.Item>
            <Form.Item name={`${this.state.prefix}_35`} noStyle>
              <Input
                {...componentStyle}
                onChange={this.handleComponentChange}
                placeholder={this.state.tensor["35"]}
                disabled={this.state.disabled["35"]}
              />
            </Form.Item>
            <Form.Item name={`${this.state.prefix}_36`} noStyle>
              <Input
                {...componentStyle}
                onChange={this.handleComponentChange}
                placeholder={this.state.tensor["36"]}
                disabled={this.state.disabled["36"]}
              />
            </Form.Item>
          </Input.Group>
        </Form.Item>
      </>
    );
  }
}

export { PiezoelectricTensor };
