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
  rank: number;
}

export type disabledDict = Record<string, boolean>;

const baseDefaultDisable: disabledDict = {
  "1": false,
};

type tensorChoices = "1";

export type tensorDict = Record<string, string>;

class TensorBase extends React.Component<PropertyInputProps, TensorInputState> {
  // indexRefList: [React.RefObject<FormInstance>];
  state: TensorInputState;

  constructor(props: PropertyInputProps) {
    super(props);

    this.state = {
      prefix: `phase${this.props.phaseIndex}_${this.props.id}`,
      rank: 0,
      symmetry: "custom",
      disabled: baseDefaultDisable,
      tensor: {
        "1": "1",
      },
    };
  }

  onImport = (tensorIn: TensorInputData) => {
    console.log("TensorBase::onImport", tensorIn);
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
      name: this.props.id,
      rank: this.state.rank,
      pointGroup: this.state.symmetry,
      component: tensor,
    };
  };

  handleComponentChange = (event: React.FormEvent<HTMLInputElement>) => {
    let ten = this.state.tensor;
    let ids = event.currentTarget.id.split("_");
    let id: tensorChoices = ids[ids.length - 1] as tensorChoices;
    ten[id] = event.currentTarget.value;
    console.log(
      "TensorBase::handleComponentChange::value",
      event.currentTarget.value
    );
    ten = this.applySymmetry(this.state.symmetry, ten);
    console.log("TensorBase::handleComponentChange::ten", ten);

    this.setState({
      tensor: ten,
    });
  };

  applySymmetry = (sym: string, ten: tensorDict): tensorDict => {
    console.log("TensorBase::applySymmetry::tensor", ten);
    let [zeroIds, fieldIds] = this.getSymmetryConstraint(sym);
    let fieldsVal: Record<string, string> = {};
    console.log("TensorBase::applySymmetry::constraints", zeroIds, fieldIds);

    let tenCopy = JSON.parse(JSON.stringify(this.state.tensor));
    [...zeroIds, ...Object.keys(fieldIds)].forEach((id) => {
      if (id in ten) {
        delete tenCopy[id];
      }
    });

    console.log("TensorBase::applySymmetry::tenCopy", tenCopy);

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
    let dis = JSON.parse(JSON.stringify(this.state.disabled));
    let fields: Record<string, string> = {};
    let ten = this.state.tensor;
    zeroIds.forEach((id) => {
      fields[`${this.state.prefix}_${id}`] = "0";
      ten[id as tensorChoices] = "0";
    });
    for (const key in dis) {
      dis[key] = false;
    }
    [...zeroIds, ...Object.keys(fieldIds)].forEach((id) => {
      dis[id] = true;
    });
    this.props.formRef.current!.setFieldsValue(fields);

    return [dis, ten];
  };

  getSymmetryConstraint = (
    sym: string
  ): [zeros: string[], fields: Record<string, string>] => {
    console.log("TensorBase::getSymmetryConstraint");
    return [[], {}];
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
    return <p> The tensor base class, replace with your class</p>;
  }
}

export { TensorBase };
