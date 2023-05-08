import React from "react";
import { Input, Form, Tooltip, Row, FormInstance } from "antd";
import type { DimensionInputData } from "@mupro/typings/DimensionInput";
import { defaultDimensionInput } from "@mupro/typings/DimensionInput";
import { marginBottom } from "@mupro/typings/Constants";
class DimensionInput extends React.Component<{}, {}> {
  formRef: React.RefObject<FormInstance>;
  constructor(props: {}) {
    super(props);
    this.formRef = React.createRef();
  }

  onFinish = (): DimensionInputData => {
    if (this.formRef.current) {
      let values = this.formRef.current.getFieldsValue(
        true
      ) as DimensionInputData;
      console.log(
        "OnFinish from the input-form-dimension component",
        this.formRef.current
      );
      return {
        nx: values["nx"],
        ny: values["ny"],
        nz: values["nz"],
        dx: values["dx"],
        dy: values["dy"],
        dz: values["dz"],
      };
    } else {
      return defaultDimensionInput;
    }
  };

  onImport(dimension: DimensionInputData) {
    console.log(
      "OnImport from the input-form-dimension component",
      dimension,
      typeof dimension.nx
    );
    if (this.formRef.current) {
      this.formRef.current.setFieldsValue({
        nx: dimension.nx.trim(),
        ny: dimension.ny.trim(),
        nz: dimension.nz.trim(),
        dx: dimension.dx.trim(),
        dy: dimension.dy.trim(),
        dz: dimension.dz.trim(),
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
        <Form.Item label="System Dimension" {...formItemStyle}>
          <Tooltip
            title="The system size in the unit of simulation grid points along x, y, and z axis, respectively. Must be integer."
            placement="bottomLeft"
          >
            <Input.Group compact>
              <Form.Item
                name="nx"
                noStyle
                rules={[
                  {
                    required: true,
                    message: "nx is required",
                  },
                ]}
              >
                <Input style={{ width: "33.3%" }} placeholder="100" />
              </Form.Item>
              <Form.Item
                name="ny"
                noStyle
                rules={[
                  {
                    required: true,
                    message: "ny is required",
                  },
                ]}
              >
                <Input style={{ width: "33.3%" }} placeholder="100" />
              </Form.Item>
              <Form.Item
                name="nz"
                noStyle
                rules={[
                  {
                    required: true,
                    message: "nz is required",
                  },
                ]}
              >
                <Input style={{ width: "33.3%" }} placeholder="100" />
              </Form.Item>
            </Input.Group>
          </Tooltip>
        </Form.Item>
        <Form.Item label="Dimension Unit (m)" {...formItemStyle}>
          <Tooltip
            title="The dimension, in the unit of meter, of each simulation grid point represent along x, y, and z axis, respectively."
            placement="bottomLeft"
          >
            <Input.Group compact>
              <Form.Item
                name="dx"
                noStyle
                rules={[
                  {
                    required: true,
                    message: "dx is required",
                  },
                ]}
              >
                <Input style={{ width: "33.3%" }} placeholder="1.5e-7" />
              </Form.Item>
              <Form.Item
                name="dy"
                noStyle
                rules={[
                  {
                    required: true,
                    message: "dy is required",
                  },
                ]}
              >
                <Input style={{ width: "33.3%" }} placeholder="1.5e-7" />
              </Form.Item>
              <Form.Item
                name="dz"
                noStyle
                rules={[
                  {
                    required: true,
                    message: "dz is required",
                  },
                ]}
              >
                <Input style={{ width: "33.3%" }} placeholder="1.5e-7" />
              </Form.Item>
            </Input.Group>
          </Tooltip>
        </Form.Item>
      </Form>
    );
  }
}

export { DimensionInput };
