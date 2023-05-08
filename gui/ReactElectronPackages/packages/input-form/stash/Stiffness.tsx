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
  "13": boolean;
  "14": boolean;
  "15": boolean;
  "16": boolean;
  "22": boolean;
  "23": boolean;
  "24": boolean;
  "25": boolean;
  "26": boolean;
  "33": boolean;
  "34": boolean;
  "35": boolean;
  "36": boolean;
  "44": boolean;
  "45": boolean;
  "46": boolean;
  "55": boolean;
  "56": boolean;
  "66": boolean;
}

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

type tensorChoices =
  | "11"
  | "12"
  | "13"
  | "14"
  | "15"
  | "16"
  | "22"
  | "23"
  | "24"
  | "25"
  | "26"
  | "33"
  | "34"
  | "35"
  | "36"
  | "44"
  | "45"
  | "46"
  | "55"
  | "56"
  | "66";

type tensorDict = Record<tensorChoices, string>;

class StiffnessTensor extends React.Component<
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
      },
    };
  }

  onImport = (tensorIn: TensorInputData) => {
    console.log("StiffnessTensor::onImport", tensorIn);
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
          value: values[`${this.state.prefix}_${id}`],
          index: [`${id}`],
        });
        console.log("tensor", this.state.prefix, tensor);
      }
    });
    return {
      name: this.props.tensorName.replace(" ", "_"),
      rank: 4,
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

  applySymmetry = (sym: string, ten: tensorDict): tensorDict => {
    let [zeroIds, fieldIds] = this.getSymmetryConstraint(sym);
    let fieldsVal: Record<string, string> = {};

    let tenCopy = JSON.parse(JSON.stringify(this.state.tensor));
    [...zeroIds, ...Object.keys(fieldIds)].forEach((id) => {
      if (id in ten) {
        delete tenCopy[id];
      }
    });

    for (const key in fieldIds) {
      //replace
      Object.keys(tenCopy).forEach((id) => {
        fieldIds[key] = fieldIds[key].replace(`@${id}`, tenCopy[id]);
      });

      //eval
      let val = evaluate(fieldIds[key]);
      fieldsVal[`${this.state.prefix}_${key}`] = val;
      ten[key as tensorChoices] = val.toString();
      // console.log("eval", key, val, ten, fieldIds);
    }
    // console.log("ten symmetry", ten);
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
      case "triclinic":
        return [[], {}];
      case "monoclinic":
        return [["14", "16", "24", "26", "34", "36", "45", "56"], {}];
      case "orthorhombic":
        return [
          ["14", "15","16", "24","25", "26", "34","35", "36", "45","46", "56"], // prettier-ignore
          {},
        ];
      case "tetragonal_1":
        return [
          ["14", "15", "24","25", "34","35", "36", "45","46", "56"], // prettier-ignore
          { "26": "-@16", "55": "@44", "23": "@13", "22": "@11" },
        ];
      case "tetragonal_2":
        return [
          ["14", "15","16", "24","25", "26", "34","35", "36", "45","46", "56"], // prettier-ignore
          { "55": "@44", "23": "@13", "22": "@11" },
        ];
      case "trigonal_1":
        return [
          ["16", "26", "34","35", "36", "45"], // prettier-ignore
          { "55": "@44", "23": "@13" ,"24":"-@14","15":"-@25","46":"@25","56":"@14","66":"0.5*(@11-@12)","22":"@11"}, // prettier-ignore
        ];
      case "trigonal_2":
        return [
          ["15","16", "25","26", "34","35", "36", "45","46"], // prettier-ignore
          { "55": "@44", "23": "@13" ,"24":"-@14","56":"@14","66":"0.5*(@11-@12)","22":"@11"}, // prettier-ignore
        ];
      case "hexagonal":
        return [
          ["14","15","16", "24","25","26", "34","35", "36", "45","46","56"], // prettier-ignore
          { "55": "@44", "23": "@13" ,"66":"0.5*(@11-@12)","22":"@11"}, // prettier-ignore
        ];
      case "cubic":
        return [
          ["14","15","16", "24","25","26", "34","35", "36", "45","46","56"], // prettier-ignore
          { "55": "@44", "13":"@12","23": "@12" ,"66":"@44" ,"22":"@11","33":"@11"}, // prettier-ignore
        ];
      case "isotropic":
        return [
          ["14","15","16", "24","25","26", "34","35", "36", "45","46","56"], // prettier-ignore
          { "44":"0.5*(@11-@12)","55": "0.5*(@11-@12)", "13":"@12","23": "@12" ,"66":"0.5*(@11-@12)","22":"@11","33":"@11"}, // prettier-ignore
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
              Iostropic(&infin;&infin;, &infin;&infin;m)
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
                <Input style={{ width: "33%" }} placeholder="100" />
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
                <Input style={{ width: "33%" }} placeholder="0.3" />
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
