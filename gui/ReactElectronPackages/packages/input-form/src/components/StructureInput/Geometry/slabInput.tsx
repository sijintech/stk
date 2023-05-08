import React from "react";
import { Input, Form, Tooltip } from "antd";
import type { GeometryInputProps } from "./geometryInput";
import type { SlabInputData } from "@mupro/typings/GeometryInput";

class SlabInput extends React.Component<GeometryInputProps, {}> {
  onImport = (geometry: SlabInputData) => {
    if (!this.props.formRef.current) return undefined;
    let i = this.props.index;
    console.log("onImport from the Slab", i, geometry);
    this.props.formRef.current.setFieldsValue({
      [`geometry${i}_centerX`]: geometry.centerX.trim(),
      [`geometry${i}_centerY`]: geometry.centerY.trim(),
      [`geometry${i}_centerZ`]: geometry.centerZ.trim(),
      [`geometry${i}_normalX`]: geometry.normalX.trim(),
      [`geometry${i}_normalY`]: geometry.normalY.trim(),
      [`geometry${i}_normalZ`]: geometry.normalZ.trim(),
      [`geometry${i}_thickness`]: geometry.thickness.trim(),
      [`geometry${i}_label`]: geometry.label.trim(),
      [`geometry${i}_matrixLabel`]: geometry.matrixLabel.trim(),
    });
  };

  onFinish = (values: any): SlabInputData => {
    let i = this.props.index;
    console.log("onFinish from the Slab", i, values);
    return {
      type: "slab",
      centerX: values[`geometry${i}_centerX`],
      centerY: values[`geometry${i}_centerY`],
      centerZ: values[`geometry${i}_centerZ`],
      normalX: values[`geometry${i}_normalX`],
      normalY: values[`geometry${i}_normalY`],
      normalZ: values[`geometry${i}_normalZ`],
      thickness: values[`geometry${i}_thickness`],
      label: values[`geometry${i}_label`],
      matrixLabel: values[`geometry${i}_matrixLabel`],
    };
  };

  render() {
    const formStyle = {
      labelCol: { span: 8 },
      wrapperCol: { span: 16 },
      style: { width: "100%" },
    };
    let i = this.props.index;
    return (
      <div>
        <Form.Item label="Center">
          <Tooltip
            title={`The center x, y, and z coordinate for geometry${i}, may use floating number`}
            placement="bottomLeft"
          >
            <Input.Group compact>
              <Form.Item
                name={`geometry${i}_centerX`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "geometry center x coordinate is required",
                  },
                ]}
              >
                <Input style={{ width: "33%" }} placeholder="10" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_centerY`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "geometry center y coordinate is required",
                  },
                ]}
              >
                <Input style={{ width: "33%" }} placeholder="10" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_centerZ`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "geometry center z coordinate is required",
                  },
                ]}
              >
                <Input style={{ width: "33%" }} placeholder="10" />
              </Form.Item>
            </Input.Group>
          </Tooltip>
        </Form.Item>

        <Form.Item label="Normal" {...formStyle}>
          <Tooltip
            title={`The vector of normal direction for the geometry${i}`}
            placement="bottomLeft"
          >
            <Input.Group compact>
              <Form.Item
                name={`geometry${i}_normalX`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "geometry normal x component is required",
                  },
                ]}
              >
                <Input style={{ width: "33%" }} placeholder="10" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_normalY`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "geometry normal y component is required",
                  },
                ]}
              >
                <Input style={{ width: "33%" }} placeholder="10" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_normalZ`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "geometry normal z component is required",
                  },
                ]}
              >
                <Input style={{ width: "33%" }} placeholder="10" />
              </Form.Item>
            </Input.Group>
          </Tooltip>
        </Form.Item>

        <Form.Item label="Thickness" {...formStyle}>
          <Tooltip title="Thickness for the geometry" placement="bottomLeft">
            <Form.Item
              name={`geometry${i}_thickness`}
              noStyle
              rules={[
                { required: true, message: "geometry thickness is required" },
              ]}
            >
              <Input style={{ width: "33%" }} placeholder="10" />
            </Form.Item>
          </Tooltip>
        </Form.Item>

        <Form.Item label="Label" {...formStyle}>
          <Tooltip
            title="The phase label for the current geometry"
            placement="bottomLeft"
          >
            <Form.Item
              name={`geometry${i}_label`}
              noStyle
              rules={[
                { required: true, message: "The phase label is required" },
              ]}
            >
              <Input style={{ width: "33%" }} placeholder="0" />
            </Form.Item>
          </Tooltip>
        </Form.Item>

        <Form.Item label="matrixLabel" {...formStyle}>
          <Tooltip
            title="The matrix label for the current geometry"
            placement="bottomLeft"
          >
            <Form.Item
              name={`geometry${i}_matrixLabel`}
              noStyle
              rules={[
                { required: true, message: "The matrix label is required" },
              ]}
            >
              <Input style={{ width: "33%" }} placeholder="0" />
            </Form.Item>
          </Tooltip>
        </Form.Item>
      </div>
    );
  }
}

export { SlabInput };
