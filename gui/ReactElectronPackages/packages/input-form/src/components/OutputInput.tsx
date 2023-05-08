import React from "react";
import { Form, Tooltip, Select, InputNumber, Row, FormInstance } from "antd";
const { Option } = Select;
import type { OutputInputData } from "@mupro/typings/OutputInput";
import { defaultOutputInput } from "@mupro/typings/OutputInput";
import { marginBottom } from "@mupro/typings/Constants";
interface OutputInputProps {
  noFrequency: boolean;
}

class OutputInput extends React.Component<OutputInputProps, {}> {
  formRef: React.RefObject<FormInstance>;

  constructor(props: OutputInputProps) {
    super(props);
    this.formRef = React.createRef();
  }

  onFinish = (): OutputInputData => {
    if (this.formRef.current) {
      let values = this.formRef.current.getFieldsValue(true) as OutputInputData;
      console.log(
        "The finish from output input",
        values,
        this.props.noFrequency
      );
      if (this.props.noFrequency === false) {
        return {
          format: values.format,
          frequency: values.frequency,
        };
      } else {
        return {
          format: values.format,
        };
      }
    } else {
      return defaultOutputInput;
    }
  };

  onImport = (output: OutputInputData) => {
    if (this.formRef.current) {
      console.log(
        "the import from output input",
        output,
        this.props.noFrequency
      );
      if (this.props.noFrequency === false) {
        console.log("going through the no freq");
        this.formRef.current.setFieldsValue({
          format: output.format.trim(),
          frequency: Number(output.frequency!.trim()),
        });
      } else {
        this.formRef.current.setFieldsValue({
          format: output.format.trim(),
        });
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
      <Form {...formStyle} ref={this.formRef}>
        <Tooltip title="The output format for 3D data" placement="top">
          <Form.Item name="format" label="Output Format" {...formItemStyle}>
            <Select placeholder="Select the output file format">
              <Option value="vti">vti</Option>
              <Option value="dat">dat</Option>
            </Select>
          </Form.Item>
        </Tooltip>
        {this.props.noFrequency == false ? (
          <Tooltip
            title="The frequency that simulation output 3D system snapshot"
            placement="bottom"
          >
            <Form.Item
              label="Output frequency"
              name="frequency"
              {...formItemStyle}
            >
              <InputNumber min={1} placeholder="10" />
            </Form.Item>
          </Tooltip>
        ) : null}
      </Form>
    );
  }

  static defaultProps = {
    noFrequency: false,
  };
}

export { OutputInput };
