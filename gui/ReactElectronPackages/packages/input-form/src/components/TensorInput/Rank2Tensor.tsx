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
  "12": false,
  "13": false,
  "22": false,
  "23": false,
  "33": false,
};

class Rank2Tensor extends TensorBase {
  // indexRefList: [React.RefObject<FormInstance>];

  constructor(props: PropertyInputProps) {
    super(props);

    this.state = {
      prefix: `phase${this.props.phaseIndex}_${this.props.id}`,
      rank: 2,
      symmetry: "custom",
      disabled: defaultDisable,
      tensor: {
        "11": "11",
        "12": "12",
        "13": "13",
        "22": "22",
        "23": "23",
        "33": "33",
      },
    };
  }

  getSymmetryConstraint = (
    sym: string
  ): [zeros: string[], fields: Record<string, string>] => {
    switch (sym) {
      case "triclinic":
        return [[], {}];
      case "monoclinic":
        return [["12", "23"], {}];
      case "orthorhombic": // "cubic",  "uniaxial"， ""
        return [["12", "23", "13"], {}];
      case "uniaxial": // "cubic",  "uniaxial"， "orthorhombic"
        console.log("the symmetry constraint uni", sym);
        return [["12", "23", "13"], { "22": "@11" }];
      case "cubic": // "cubic"
        return [["12", "23", "13"], { "22": "@11", "33": "@11" }];
      default:
        return [[], {}];
    }
  };

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
        <Form.Item
          label="Symmetry"
          name={`${this.state.prefix}_symmetry`}
          {...formItemStyle}
        >
          <Select
            placeholder="Select the tensor symmetry"
            onChange={this.onSelectTensorSymmetry}
          >
            <Option value={"triclinic"}>
              Triclinic(1,
              <span style={{ textDecoration: "overline" }}>1</span>)
            </Option>
            <Option value={"monoclinic"}>Monoclinic(2, m, 2/m)</Option>
            <Option value={"orthorhombic"}>Orthorhombic(222, mm2, mmm)</Option>
            <Option value={"uniaxial"}>
              Uniaxial(3,
              <span style={{ textDecoration: "overline" }}>3</span>, 32, 3m,{" "}
              <span style={{ textDecoration: "overline" }}>3</span>m, 4,{" "}
              <span style={{ textDecoration: "overline" }}>4</span>, 4/m, 422,
              4mm, <span style={{ textDecoration: "overline" }}>4</span>2m,
              4/mmm, 6, <span style={{ textDecoration: "overline" }}>6</span>,
              6/m, 622, 6mm,
              <span style={{ textDecoration: "overline" }}>6</span>m2, 6/mmm,
              &infin;, &infin;m, &infin;/m, &infin;2, &infin;/mm)
            </Option>
            <Option value={"cubic"}>
              Cubic(23, m<span style={{ textDecoration: "overline" }}>3</span>,
              432, <span style={{ textDecoration: "overline" }}>4</span>3m, m
              <span style={{ textDecoration: "overline" }}>3</span>m,
              &infin;&infin;, &infin;&infin;m)
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
          </Input.Group>
        </Form.Item>
        <Form.Item {...tensorStyle}>
          <Input.Group compact>
            <Form.Item name={`${this.state.prefix}_21`} noStyle>
              <Input
                {...componentStyle}
                placeholder={this.state.tensor["12"]}
                disabled
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
                placeholder={this.state.tensor["23"]}
                disabled={this.state.disabled["23"]}
                onChange={this.handleComponentChange}
              />
            </Form.Item>
          </Input.Group>
        </Form.Item>
        <Form.Item {...tensorStyle}>
          <Input.Group compact>
            <Form.Item name={`${this.state.prefix}_31`} noStyle>
              <Input
                {...componentStyle}
                placeholder={this.state.tensor["13"]}
                disabled
              />
            </Form.Item>
            <Form.Item name={`${this.state.prefix}_32`} noStyle>
              <Input
                {...componentStyle}
                placeholder={this.state.tensor["23"]}
                disabled
              />
            </Form.Item>
            <Form.Item name={`${this.state.prefix}_33`} noStyle>
              <Input
                {...componentStyle}
                placeholder={this.state.tensor["33"]}
                disabled={this.state.disabled["33"]}
                onChange={this.handleComponentChange}
              />
            </Form.Item>
          </Input.Group>
        </Form.Item>
      </>
    );
  }
}

export { Rank2Tensor };
