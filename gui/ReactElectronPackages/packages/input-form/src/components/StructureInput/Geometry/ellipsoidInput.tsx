import React from "react";
import { Input, Form, Tooltip } from "antd";
import type { GeometryInputProps } from "./geometryInput";
import type { EllipsoidInputData } from "@mupro/typings/GeometryInput";

class EllipsoidInput extends React.Component<GeometryInputProps, {}> {
  onImport = (geometry: EllipsoidInputData) => {
    if (!this.props.formRef.current) return;
    let i = this.props.index;
    console.log("onImport from Ellipsoid ", i, geometry);
    this.props.formRef.current.setFieldsValue({
      [`geometry${i}_centerX`]: geometry.centerX.trim(),
      [`geometry${i}_centerY`]: geometry.centerY.trim(),
      [`geometry${i}_centerZ`]: geometry.centerZ.trim(),
      [`geometry${i}_radiusX`]: geometry.radiusX.trim(),
      [`geometry${i}_radiusY`]: geometry.radiusY.trim(),
      [`geometry${i}_radiusZ`]: geometry.radiusZ.trim(),
      [`geometry${i}_rotationX`]: geometry.rotationX.trim(),
      [`geometry${i}_rotationY`]: geometry.rotationY.trim(),
      [`geometry${i}_rotationZ`]: geometry.rotationZ.trim(),
      [`geometry${i}_label`]: geometry.label.trim(),
      [`geometry${i}_matrixLabel`]: geometry.matrixLabel.trim(),
    });
  };

  onFinish = (values: any): EllipsoidInputData => {
    let i = this.props.index;
    console.log("onFinish from Ellipsoid", i, values);
    return {
      type: "ellipsoid",
      centerX: values[`geometry${i}_centerX`],
      centerY: values[`geometry${i}_centerY`],
      centerZ: values[`geometry${i}_centerZ`],
      radiusX: values[`geometry${i}_radiusX`],
      radiusY: values[`geometry${i}_radiusY`],
      radiusZ: values[`geometry${i}_radiusZ`],
      rotationX: values[`geometry${i}_rotationX`],
      rotationY: values[`geometry${i}_rotationY`],
      rotationZ: values[`geometry${i}_rotationZ`],
      label: values[`geometry${i}_label`],
      matrixLabel: values[`geometry${i}_matrixLabel`],
    };
  };

  render() {
    let i = this.props.index;
    return (
      <div>
        <Form.Item
          label="Center"
          labelCol={{ span: 8 }}
          wrapperCol={{ span: 16 }}
        >
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
                <Input style={{ width: "33%" }} placeholder="50" />
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
                <Input style={{ width: "33%" }} placeholder="50" />
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
                <Input style={{ width: "33%" }} placeholder="50" />
              </Form.Item>
            </Input.Group>
          </Tooltip>
        </Form.Item>

        <Form.Item label="Radius">
          <Tooltip
            title={`The radius along x, y, z of the geometry${i}`}
            placement="bottomLeft"
          >
            <Input.Group compact>
              <Form.Item
                name={`geometry${i}_radiusX`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "geometry radius x component is required",
                  },
                ]}
              >
                <Input style={{ width: "33%" }} placeholder="10" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_radiusY`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "geometry radius y component is required",
                  },
                ]}
              >
                <Input style={{ width: "33%" }} placeholder="10" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_radiusZ`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "geometry radius z component is required",
                  },
                ]}
              >
                <Input style={{ width: "33%" }} placeholder="10" />
              </Form.Item>
            </Input.Group>
          </Tooltip>
        </Form.Item>

        <Form.Item label="Rotation">
          <Tooltip
            title={`The rotation along x, y, and z axis in degrees for the geometry${i}. The rotation sequence is xyz.`}
            placement="bottomLeft"
          >
            <Input.Group compact>
              <Form.Item
                name={`geometry${i}_rotationX`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "geometry rotation along x is required",
                  },
                ]}
              >
                <Input style={{ width: "33%" }} placeholder="0" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_rotationY`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "geometry rotation along y is required",
                  },
                ]}
              >
                <Input style={{ width: "33%" }} placeholder="0" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_rotationZ`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "geometry rotation along z is required",
                  },
                ]}
              >
                <Input style={{ width: "33%" }} placeholder="0" />
              </Form.Item>
            </Input.Group>
          </Tooltip>
        </Form.Item>

        <Form.Item label="Label">
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
        <Form.Item label="matrixLabel">
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

export { EllipsoidInput };
