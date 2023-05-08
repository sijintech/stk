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

const { Option } = Select;

interface TensorInputState {
  prefix: string;
  symmetry: string;
  disabled: disabledDict;
  tensor: tensorDict;
}

interface disabledDict {
  "11": boolean;
  "12": boolean;
  "13": boolean;
  "14": boolean;
  "15": boolean;
  "16": boolean;
  "21": boolean;
  "22": boolean;
  "23": boolean;
  "24": boolean;
  "25": boolean;
  "26": boolean;
  "31": boolean;
  "32": boolean;
  "33": boolean;
  "34": boolean;
  "35": boolean;
  "36": boolean;
}

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
type tensorChoices =
  | "11"
  | "12"
  | "13"
  | "14"
  | "15"
  | "16"
  | "21"
  | "22"
  | "23"
  | "24"
  | "25"
  | "26"
  | "31"
  | "32"
  | "33"
  | "34"
  | "35"
  | "36";

type tensorDict = Record<tensorChoices, string>;

class PiezomagneticTensor extends React.Component<
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

  onImport = (tensorIn: TensorInputData) => {
    console.log("PiezomagneticTensor::onImport", tensorIn);
    if (this.props.formRef.current) {
      let sym = tensorIn.pointGroup.trim();
      this.props.formRef.current!.setFieldsValue({
        [`${this.state.prefix}_symmetry`]: sym,
      });

      let fieldsVal: Record<string, string> = {};
      let [dis, ten] = this.setZeroDisableComponent(sym);

      tensorIn.component.forEach((comp) => {
        comp.index?.forEach((ind) => {
          fieldsVal[`${this.state.prefix}_${ind}`] = comp.value;
          ten[ind as tensorChoices] = comp.value;
        });
      });

      this.props.formRef.current!.setFieldsValue(fieldsVal);

      ten = this.applySymmetry(sym, ten);

      this.setState({
        symmetry: sym,
        tensor: ten,
        disabled: dis,
      });
    }
  };

  onFinish = (values: any): TensorInputData => {
    var tensor: TensorComponentData[] = [];

    let [zeroIds, relationIds] = this.getSymmetryConstraint(
      this.state.symmetry
    );

    Object.keys(this.state.tensor).forEach((id) => {
      if (![...zeroIds, ...Object.keys(relationIds)].includes(id)) {
        tensor.push({
          index: [`${id}`],
          value: values[`${this.state.prefix}_${id}`],
        });
        console.log("tensor", this.state.prefix, tensor);
      }
    });

    return {
      name: this.props.tensorName.replace(" ", "_"),
      rank: 3,
      pointGroup: this.state.symmetry,
      component: tensor,
    };
  };

  handleComponentChange = (event: React.FormEvent<HTMLInputElement>) => {
    let ten = this.state.tensor;
    let ids = event.currentTarget.id.split("_");
    let id: tensorChoices = ids[ids.length - 1] as tensorChoices;
    ten[id] = event.currentTarget.value;
    ten = this.applySymmetry(this.state.symmetry, ten);
    this.setState({
      tensor: ten,
    });
  };

  applySymmetry = (sym: string, ten: tensorDict) => {
    let [zeroIds, fieldIds] = this.getSymmetryConstraint(sym);
    let fieldsVal: Record<string, string> = {};
    let tenCopy = JSON.parse(JSON.stringify(this.state.tensor));
    // let ten = this.state.tensor;
    [...zeroIds, ...Object.keys(fieldIds)].forEach((id) => {
      if (id in ten) {
        delete tenCopy[id];
      }
    });
    // console.log("tenids", Object.keys(ten), [
    //   ...zeroIds,
    //   ...Object.keys(fieldIds),
    // ]);
    for (const key in fieldIds) {
      //replace
      Object.keys(tenCopy).forEach((id) => {
        fieldIds[key] = fieldIds[key].replace(`@${id}`, tenCopy[id]);
      });

      //eval
      let val = evaluate(fieldIds[key]);
      fieldsVal[`${this.state.prefix}_${key}`] = val;
      ten[key as tensorChoices] = val.toString();
      console.log("eval", key, val, ten, fieldIds);
    }
    console.log("ten symmetry", ten);
    this.props.formRef.current!.setFieldsValue(fieldsVal);
    return ten;
    // this.setState({
    //   tensor: ten,
    // });
  };

  setZeroDisableComponent = (
    sym: string
  ): [dis: disabledDict, ten: tensorDict] => {
    let [zeroIds, fieldIds] = this.getSymmetryConstraint(sym);
    let dis = JSON.parse(JSON.stringify(defaultDisable));
    let fields: Record<string, string> = {};
    let ten = this.state.tensor;
    zeroIds.forEach((id) => {
      fields[`${this.state.prefix}_${id}`] = "0";
      ten[id as tensorChoices] = "0";
    });
    [...zeroIds, ...Object.keys(fieldIds)].forEach((id) => {
      dis[id] = true;
    });
    this.props.formRef.current!.setFieldsValue(fields);

    return [dis, ten];
  };

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
      case "2prime":
        return [
          ["14", "16", "21","22","23","25", "34","36"], // prettier-ignore
          {},
        ];
      case "222":
        return [
          ["11", "12", "13", "15","16", "21","22","23","24", "26","31","32","33", "34", "35"], // prettier-ignore
          {},
        ];
      case "2prime2prime2":
        return [
          ["11", "12", "13", "14","16", "21","22","23","25", "26", "34", "35", "36"], // prettier-ignore
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
      case "32prime":
        return [
          ["23","25","26", "11","12","13","14", "34","35", "36"], // prettier-ignore
          {"21":"-@22","16":"-2*@22",  "24": "@15" ,"32":"@31"}, // prettier-ignore
        ];
      case "4":
        return [
          ["21","22","23","26", "11","12","13","16", "34","35", "36"], // prettier-ignore
          { "25": "-@14", "24": "@15" ,"32":"@31"}, // prettier-ignore
        ];
      case "4prime":
        return [
          ["21","22","23","26", "11","12","13","16", "33","34","35"], // prettier-ignore
          { "25": "@14", "24": "-@15" ,"32":"-@31"}, // prettier-ignore
        ];
      case "422":
        return [
          ["21","22","23","24","26", "11","12","13","15","16", "31","32","33","34","35", "36"], // prettier-ignore
          { "25": "-@14"}, // prettier-ignore
        ];
      case "4prime22":
        return [
          ["21","22","23","24","26", "11","12","13","15","16", "31","32","33","34","35"], // prettier-ignore
          { "25": "@14"}, // prettier-ignore
        ];
      case "42prime2prime":
        return [
          ["21","22","23","25","26", "11","12","13","14","16", "34","35", "36"], // prettier-ignore
          { "24": "@15" ,"32":"@31"}, // prettier-ignore
        ];
      case "6prime":
        return [
          ["23","24","25", "13","14","15", "31","32","33","34","35","36"], // prettier-ignore
          { "12": "-@11","21":"-@22","16":"-2*@22","26":"-2*@11"}, // prettier-ignore
        ];
      case "6prime22prime":
        return [
          ["13","14","15","16", "21","22","23","24","25", "31","32","33","34","35","36"], // prettier-ignore
          { "12":"-@11","26":"-2*@11"}, // prettier-ignore
        ];
      case "23":
        return [
          ["21","22","23","24","26", "11","12","13","15","16", "31","32","33","34","35"], // prettier-ignore
          { "25":"@14","36":"@14"}, // prettier-ignore
        ];
      default:
        return [[], {}];
    }
  };

  onSelectTensorSymmetry = (values: string) => {
    console.log("select tensor symmetry ", values);
    let [dis, ten] = this.setZeroDisableComponent(values);
    console.log("ten", ten);
    ten = this.applySymmetry(values, ten);
    this.setState({
      symmetry: values,
      tensor: ten,
      disabled: dis,
    });
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
            <Option value={"1"}>
              1, <span style={{ textDecoration: "overline" }}>1</span>
            </Option>
            <Option value={"2"}>2, m 2/m</Option>
            <Option value={"2prime"}>2', m', 2'/m' </Option>
            <Option value={"222"}>222, mm2, mmm</Option>
            <Option value={"2prime2prime2"}>2'2'2, m'm'2, m'm'm</Option>
            <Option value={"3"}>
              3, <span style={{ textDecoration: "overline" }}>3</span>
            </Option>
            <Option value={"32"}>
              32, 3m, <span style={{ textDecoration: "overline" }}>3</span>m
            </Option>
            <Option value={"32prime"}>
              32', 3m', <span style={{ textDecoration: "overline" }}>3</span>
              m'
            </Option>
            <Option value={"4"}>
              4, <span style={{ textDecoration: "overline" }}>4</span>,4/m,6,
              <span style={{ textDecoration: "overline" }}>6</span>
              ,6/m,&infin;,&infin;/m
            </Option>
            <Option value={"4prime"}>
              4',<span style={{ textDecoration: "overline" }}>4</span>',4'/m
            </Option>
            <Option value={"422"}>
              422,4mm,<span style={{ textDecoration: "overline" }}>4</span>
              2m,4/mmm,622,6mm,
              <span style={{ textDecoration: "overline" }}>6</span>
              m2,6/mmm,&infin;2
            </Option>
            <Option value={"4prime22"}>
              4'22,4'mm',<span style={{ textDecoration: "overline" }}>4</span>
              '2m',<span style={{ textDecoration: "overline" }}>4</span>
              '2'm, 4'/mmm'
            </Option>
            <Option value={"6prime"}>
              6', <span style={{ textDecoration: "overline" }}>6</span>',6'/m'
            </Option>
            <Option value={"6prime22prime"}>
              6'22', 6'mm',
              <span style={{ textDecoration: "overline" }}>6</span>'m'2,
              <span style={{ textDecoration: "overline" }}>6</span>
              m2', 6'/m'mm'
            </Option>
            <Option value={"23"}>
              23,m3,4'32,
              <span style={{ textDecoration: "overline" }}>4</span>'3m',m3m'
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

export { PiezomagneticTensor };
