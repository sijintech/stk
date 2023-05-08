import React from "react";
import { Input, Form, Tooltip, Row, FormInstance } from "antd";
import { marginBottom } from "@mupro/typings/Constants";
class NameInput extends React.Component<{}, {}> {
  formRef: React.RefObject<FormInstance>;
  constructor(props: {}) {
    super(props);
    this.formRef = React.createRef();
  }

  onFinish = (): string => {
    if (this.formRef.current) {
      let values = this.formRef.current.getFieldsValue(true);
      console.log(
        "OnFinish from the input-form-dimension component",
        this.formRef.current
      );
      return values["name"];
    } else {
      return "Name for your input file";
    }
  };

  onImport(name: string) {
    console.log("OnImport from the input-form-dimension component", name);
    if (this.formRef.current) {
      this.formRef.current.setFieldsValue({
        name: name.trim(),
      });
    }
  }

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
        <Form.Item label="Name" {...formItemStyle}>
          <Form.Item name="name" noStyle>
            <Input placeholder="Set a name for your input file" />
          </Form.Item>
        </Form.Item>
      </Form>
    );
  }
}

export { NameInput };
