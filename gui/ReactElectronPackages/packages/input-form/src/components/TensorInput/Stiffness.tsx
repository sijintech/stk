import React from "react";
import { Input, Form, Tooltip, Select, FormInstance } from "antd";
import type {
  TensorInputData,
  TensorComponentData,
} from "@mupro/typings/TensorInput";
import { defaultTensorInput } from "@mupro/typings/TensorInput";
import { marginBottom } from "@mupro/typings/Constants";
import { evaluate } from "mathjs";
// import {log } from "log";
import type { PropertyInputProps } from ".";
import { TensorBase, disabledDict, tensorDict } from "./TensorBase";

const { Option } = Select;

const defaultDisable: disabledDict = {
  "13": false,
  "14": false,
  "15": false,
  "16": false,
  "22": false,
  "23": false,
  "24": false,
  "25": false,
  "26": false,
  "33": false,
  "34": false,
  "35": false,
  "36": false,
  "44": false,
  "45": false,
  "46": false,
  "55": false,
  "56": false,
  "66": false,
};

class StiffnessTensor extends TensorBase {
  // indexRefList: [React.RefObject<FormInstance>];

  constructor(props: PropertyInputProps) {
    super(props);

    this.state = {
      prefix: `phase${this.props.phaseIndex}_${this.props.id}`,
      rank: 4,
      symmetry: "custom",
      disabled: defaultDisable,
      tensor: {
        "11": "11",
        "12": "12",
        "13": "13",
        "14": "14",
        "15": "15",
        "16": "16",
        "22": "22",
        "23": "23",
        "24": "24",
        "25": "25",
        "26": "26",
        "33": "33",
        "34": "34",
        "35": "35",
        "36": "36",
        "44": "44",
        "45": "45",
        "46": "46",
        "55": "55",
        "56": "56",
        "66": "66",
        young: "100",
        poisson: "0.3",
      },
    };
  }

  getSymmetryConstraint = (
    sym: string
  ): [zeros: string[], fields: Record<string, string>] => {
    switch (sym) {
      case "triclinic":
        return [["young", "poisson"], {}];
      case "monoclinic":
        return [
          ["14", "16", "24", "26", "34", "36", "45", "56", "young", "poisson"],
          {},
        ];
      case "orthorhombic":
        return [
          ["14", "15","16", "24","25", "26", "34","35", "36", "45","46", "56","young","poisson"], // prettier-ignore
          {},
        ];
      case "tetragonal_1":
        return [
          ["14", "15", "24","25", "34","35", "36", "45","46", "56","young","poisson"], // prettier-ignore
          { "26": "-@16", "55": "@44", "23": "@13", "22": "@11" },
        ];
      case "tetragonal_2":
        return [
          ["14", "15","16", "24","25", "26", "34","35", "36", "45","46", "56","young","poisson"], // prettier-ignore
          { "55": "@44", "23": "@13", "22": "@11" },
        ];
      case "trigonal_1":
        return [
          ["16", "26", "34","35", "36", "45","young","poisson"], // prettier-ignore
          { "55": "@44", "23": "@13" ,"24":"-@14","15":"-@25","46":"@25","56":"@14","66":"0.5*(@11-@12)","22":"@11"}, // prettier-ignore
        ];
      case "trigonal_2":
        return [
          ["15","16", "25","26", "34","35", "36", "45","46","young","poisson"], // prettier-ignore
          { "55": "@44", "23": "@13" ,"24":"-@14","56":"@14","66":"0.5*(@11-@12)","22":"@11"}, // prettier-ignore
        ];
      case "hexagonal":
        return [
          ["14","15","16", "24","25","26", "34","35", "36", "45","46","56","young","poisson"], // prettier-ignore
          { "55": "@44", "23": "@13" ,"66":"0.5*(@11-@12)","22":"@11"}, // prettier-ignore
        ];
      case "cubic":
        return [
          ["14","15","16", "24","25","26", "34","35", "36", "45","46","56","young","poisson"], // prettier-ignore
          { "55": "@44", "13":"@12","23": "@12" ,"66":"@44" ,"22":"@11","33":"@11"}, // prettier-ignore
        ];
      case "isotropic":
        return [
          ["14","15","16", "24","25","26", "34","35", "36", "45","46","56","young","poisson"], // prettier-ignore
          { "44":"0.5*(@11-@12)","55": "0.5*(@11-@12)", "13":"@12","23": "@12" ,"66":"0.5*(@11-@12)","22":"@11","33":"@11"}, // prettier-ignore
        ];
      case "engineer":
        return [
          ["11","12","13","14","15","16", "22","23","24","25","26", "33","34","35", "36", "44","45","46","55","56","66"], // prettier-ignore
          { }, // prettier-ignore
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
            <Option value={"triclinic"}>
              Triclinic(1,
              <span style={{ textDecoration: "overline" }}>1</span>)
            </Option>
            <Option value={"monoclinic"}>Monoclinic(2, m, 2/m)</Option>
            <Option value={"orthorhombic"}>Orthorhombic(222, mm2, mmm)</Option>
            <Option value={"tetragonal_1"}>
              Tetragonal(4,
              <span style={{ textDecoration: "overline" }}>4</span>, 4/m)
            </Option>
            <Option value={"tetragonal_2"}>
              Tetragonal(4mm,
              <span style={{ textDecoration: "overline" }}>4</span>2m, 422,
              4/mmm)
            </Option>
            <Option value={"trigonal_1"}>
              Trigonal(3,
              <span style={{ textDecoration: "overline" }}>3</span>)
            </Option>
            <Option value={"trigonal_2"}>
              Trigonal(32, 3m,
              <span style={{ textDecoration: "overline" }}>3</span>m)
            </Option>
            <Option value={"hexagonal"}>
              Hexagonal(6,
              <span style={{ textDecoration: "overline" }}>6</span>, 6/m, 622,
              6mm,
              <span style={{ textDecoration: "overline" }}>6</span>m2, 6/mmm,
              &infin;, &infin;m, &infin;/m, &infin;2, &infin;/mm)
            </Option>
            <Option value={"cubic"}>
              Cubic(23, m<span style={{ textDecoration: "overline" }}>3</span>,
              432, <span style={{ textDecoration: "overline" }}>4</span>3m, m
              <span style={{ textDecoration: "overline" }}>3</span>m)
            </Option>
            <Option value={"isotropic"}>
              Isotropic(&infin;&infin;, &infin;&infin;m)
            </Option>
            <Option value={"engineer"}>Youngs modulus + Poisson ratio</Option>
          </Select>
        </Form.Item>

        {this.state.symmetry === "engineer" ? (
          <>
            <Tooltip
              title={`One component for ${this.props.tensorName}`}
              placement="bottom"
            >
              <Form.Item
                label="Young's modulus"
                name={`${this.state.prefix}_young`}
                {...formItemStyle}
              >
                <Input
                  style={{ width: "33%" }}
                  placeholder={this.state.tensor["young"]}
                  onChange={this.handleComponentChange}
                />
              </Form.Item>
            </Tooltip>
            <Tooltip
              title={`One component for ${this.props.tensorName}`}
              placement="bottom"
            >
              <Form.Item
                label="Poisson ratio"
                name={`${this.state.prefix}_poisson`}
                {...formItemStyle}
              >
                <Input
                  style={{ width: "33%" }}
                  placeholder={this.state.tensor["poisson"]}
                  onChange={this.handleComponentChange}
                />
              </Form.Item>
            </Tooltip>
          </>
        ) : (
          <>
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
                    placeholder={this.state.tensor["13"]}
                    disabled
                  />
                </Form.Item>
                <Form.Item name={`${this.state.prefix}_32`} noStyle>
                  <Input
                    {...componentStyle}
                    onChange={this.handleComponentChange}
                    placeholder={this.state.tensor["23"]}
                    disabled
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
            <Form.Item {...tensorStyle}>
              <Input.Group compact>
                <Form.Item name={`${this.state.prefix}_41`} noStyle>
                  <Input
                    {...componentStyle}
                    onChange={this.handleComponentChange}
                    placeholder={this.state.tensor["14"]}
                    disabled
                  />
                </Form.Item>
                <Form.Item name={`${this.state.prefix}_42`} noStyle>
                  <Input
                    {...componentStyle}
                    onChange={this.handleComponentChange}
                    placeholder={this.state.tensor["24"]}
                    disabled
                  />
                </Form.Item>
                <Form.Item name={`${this.state.prefix}_43`} noStyle>
                  <Input
                    {...componentStyle}
                    onChange={this.handleComponentChange}
                    placeholder={this.state.tensor["34"]}
                    disabled
                  />
                </Form.Item>
                <Form.Item name={`${this.state.prefix}_44`} noStyle>
                  <Input
                    {...componentStyle}
                    onChange={this.handleComponentChange}
                    placeholder={this.state.tensor["44"]}
                    disabled={this.state.disabled["44"]}
                  />
                </Form.Item>
                <Form.Item name={`${this.state.prefix}_45`} noStyle>
                  <Input
                    {...componentStyle}
                    onChange={this.handleComponentChange}
                    placeholder={this.state.tensor["45"]}
                    disabled={this.state.disabled["45"]}
                  />
                </Form.Item>
                <Form.Item name={`${this.state.prefix}_46`} noStyle>
                  <Input
                    {...componentStyle}
                    onChange={this.handleComponentChange}
                    placeholder={this.state.tensor["46"]}
                    disabled={this.state.disabled["46"]}
                  />
                </Form.Item>
              </Input.Group>
            </Form.Item>
            <Form.Item {...tensorStyle}>
              <Input.Group compact>
                <Form.Item name={`${this.state.prefix}_51`} noStyle>
                  <Input
                    {...componentStyle}
                    onChange={this.handleComponentChange}
                    placeholder={this.state.tensor["15"]}
                    disabled
                  />
                </Form.Item>
                <Form.Item name={`${this.state.prefix}_52`} noStyle>
                  <Input
                    {...componentStyle}
                    onChange={this.handleComponentChange}
                    placeholder={this.state.tensor["25"]}
                    disabled
                  />
                </Form.Item>
                <Form.Item name={`${this.state.prefix}_53`} noStyle>
                  <Input
                    {...componentStyle}
                    onChange={this.handleComponentChange}
                    placeholder={this.state.tensor["35"]}
                    disabled
                  />
                </Form.Item>
                <Form.Item name={`${this.state.prefix}_54`} noStyle>
                  <Input
                    {...componentStyle}
                    onChange={this.handleComponentChange}
                    placeholder={this.state.tensor["45"]}
                    disabled
                  />
                </Form.Item>
                <Form.Item name={`${this.state.prefix}_55`} noStyle>
                  <Input
                    {...componentStyle}
                    onChange={this.handleComponentChange}
                    placeholder={this.state.tensor["55"]}
                    disabled={this.state.disabled["55"]}
                  />
                </Form.Item>
                <Form.Item name={`${this.state.prefix}_56`} noStyle>
                  <Input
                    {...componentStyle}
                    onChange={this.handleComponentChange}
                    placeholder={this.state.tensor["56"]}
                    disabled={this.state.disabled["56"]}
                  />
                </Form.Item>
              </Input.Group>
            </Form.Item>
            <Form.Item {...tensorStyle}>
              <Input.Group compact>
                <Form.Item name={`${this.state.prefix}_61`} noStyle>
                  <Input
                    {...componentStyle}
                    onChange={this.handleComponentChange}
                    placeholder={this.state.tensor["16"]}
                    disabled
                  />
                </Form.Item>
                <Form.Item name={`${this.state.prefix}_62`} noStyle>
                  <Input
                    {...componentStyle}
                    onChange={this.handleComponentChange}
                    placeholder={this.state.tensor["26"]}
                    disabled
                  />
                </Form.Item>
                <Form.Item name={`${this.state.prefix}_63`} noStyle>
                  <Input
                    {...componentStyle}
                    onChange={this.handleComponentChange}
                    placeholder={this.state.tensor["36"]}
                    disabled
                  />
                </Form.Item>
                <Form.Item name={`${this.state.prefix}_64`} noStyle>
                  <Input
                    {...componentStyle}
                    onChange={this.handleComponentChange}
                    placeholder={this.state.tensor["46"]}
                    disabled
                  />
                </Form.Item>
                <Form.Item name={`${this.state.prefix}_65`} noStyle>
                  <Input
                    {...componentStyle}
                    onChange={this.handleComponentChange}
                    placeholder={this.state.tensor["56"]}
                    disabled
                  />
                </Form.Item>
                <Form.Item name={`${this.state.prefix}_66`} noStyle>
                  <Input
                    {...componentStyle}
                    onChange={this.handleComponentChange}
                    placeholder={this.state.tensor["66"]}
                    disabled={this.state.disabled["66"]}
                  />
                </Form.Item>
              </Input.Group>
            </Form.Item>
          </>
        )}
      </>
    );
  }
}

export { StiffnessTensor };
