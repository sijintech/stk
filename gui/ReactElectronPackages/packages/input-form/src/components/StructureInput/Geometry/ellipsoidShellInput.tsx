import React from "react";
import { Input, Form, Tooltip } from "antd";
import type { GeometryInputProps } from "./geometryInput";
import type { EllipsoidShellInputData } from "@mupro/typings/GeometryInput";

class EllipsoidShellInput extends React.Component<GeometryInputProps, {}> {
  onImport = (geometry: EllipsoidShellInputData) => {
    if (!this.props.formRef.current) return;
    let i = this.props.index;
    console.log("onImport from the EllipsoidShell", i, geometry);
    this.props.formRef.current.setFieldsValue({
      [`geometry${i}_centerXOuter`]: geometry.centerXOuter.trim(),
      [`geometry${i}_centerXInner`]: geometry.centerXInner.trim(),
      [`geometry${i}_centerYOuter`]: geometry.centerYOuter.trim(),
      [`geometry${i}_centerYInner`]: geometry.centerYInner.trim(),
      [`geometry${i}_centerZOuter`]: geometry.centerZOuter.trim(),
      [`geometry${i}_centerZInner`]: geometry.centerZInner.trim(),
      [`geometry${i}_radiusXOuter`]: geometry.radiusXOuter.trim(),
      [`geometry${i}_radiusYOuter`]: geometry.radiusYOuter.trim(),
      [`geometry${i}_radiusZOuter`]: geometry.radiusZOuter.trim(),
      [`geometry${i}_radiusXInner`]: geometry.radiusXInner.trim(),
      [`geometry${i}_radiusYInner`]: geometry.radiusYInner.trim(),
      [`geometry${i}_radiusZInner`]: geometry.radiusZInner.trim(),
      [`geometry${i}_rotationXOuter`]: geometry.rotationXOuter.trim(),
      [`geometry${i}_rotationYOuter`]: geometry.rotationYOuter.trim(),
      [`geometry${i}_rotationZOuter`]: geometry.rotationZOuter.trim(),
      [`geometry${i}_rotationXInner`]: geometry.rotationXInner.trim(),
      [`geometry${i}_rotationYInner`]: geometry.rotationYInner.trim(),
      [`geometry${i}_rotationZInner`]: geometry.rotationZInner.trim(),
      [`geometry${i}_label`]: geometry.label.trim(),
      [`geometry${i}_labelInner`]: geometry.labelInner.trim(),
      [`geometry${i}_matrixLabel`]: geometry.matrixLabel.trim(),
    });
  };

  onFinish = (values: any): EllipsoidShellInputData => {
    let i = this.props.index;
    console.log("onFinish from the EllipsoidShell", i, values);
    return {
      type: "ellipsoid_shell",
      centerXOuter: values[`geometry${i}_centerXOuter`],
      centerXInner: values[`geometry${i}_centerXInner`],
      centerYOuter: values[`geometry${i}_centerYOuter`],
      centerYInner: values[`geometry${i}_centerYInner`],
      centerZOuter: values[`geometry${i}_centerZOuter`],
      centerZInner: values[`geometry${i}_centerZInner`],
      radiusXOuter: values[`geometry${i}_radiusXOuter`],
      radiusXInner: values[`geometry${i}_radiusXInner`],
      radiusYOuter: values[`geometry${i}_radiusYOuter`],
      radiusYInner: values[`geometry${i}_radiusYInner`],
      radiusZOuter: values[`geometry${i}_radiusZOuter`],
      radiusZInner: values[`geometry${i}_radiusZInner`],
      rotationXOuter: values[`geometry${i}_rotationXOuter`],
      rotationXInner: values[`geometry${i}_rotationXInner`],
      rotationYOuter: values[`geometry${i}_rotationYOuter`],
      rotationYInner: values[`geometry${i}_rotationYInner`],
      rotationZOuter: values[`geometry${i}_rotationZOuter`],
      rotationZInner: values[`geometry${i}_rotationZInner`],
      scaleMin: values[`geometry${i}_scaleMin`],
      scaleMax: values[`geometry${i}_scaleMax`],
      label: values[`geometry${i}_label`],
      labelInner: values[`geometry${i}_labelInner`],
      matrixLabel: values[`geometry${i}_matrixLabel`],
    };
  };

  render() {
    let i = this.props.index;
    return (
      <div>
        <h4>The outer ellipsoid</h4>
        <Form.Item label="Center">
          <Tooltip
            title={`The center x, y, and z coordinate for geometry${i}, may use floating number`}
            placement="bottomLeft"
          >
            <Input.Group compact>
              <Form.Item
                name={`geometry${i}_centerXOuter`}
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
                name={`geometry${i}_centerYOuter`}
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
                name={`geometry${i}_centerZOuter`}
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
                name={`geometry${i}_radiusXOuter`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "geometry radius x component is required",
                  },
                ]}
              >
                <Input style={{ width: "33%" }} placeholder="50" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_radiusYOuter`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "geometry radius y component is required",
                  },
                ]}
              >
                <Input style={{ width: "33%" }} placeholder="50" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_radiusZOuter`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "geometry radius z component is required",
                  },
                ]}
              >
                <Input style={{ width: "33%" }} placeholder="50" />
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
                name={`geometry${i}_rotationXOuter`}
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
                name={`geometry${i}_rotationYOuter`}
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
                name={`geometry${i}_rotationZOuter`}
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

        <h4>The inner ellipsoid</h4>

        <Form.Item label="Center">
          <Tooltip
            title={`The center x, y, and z coordinate for geometry${i}, may use floating number`}
            placement="bottomLeft"
          >
            <Input.Group compact>
              <Form.Item
                name={`geometry${i}_centerXInner`}
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
                name={`geometry${i}_centerYInner`}
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
                name={`geometry${i}_centerZInner`}
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
                name={`geometry${i}_radiusXInner`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "geometry radius x component is required",
                  },
                ]}
              >
                <Input style={{ width: "33%" }} placeholder="5" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_radiusYInner`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "geometry radius y component is required",
                  },
                ]}
              >
                <Input style={{ width: "33%" }} placeholder="5" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_radiusZInner`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "geometry radius z component is required",
                  },
                ]}
              >
                <Input style={{ width: "33%" }} placeholder="5" />
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
                name={`geometry${i}_rotationXInner`}
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
                name={`geometry${i}_rotationYInner`}
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
                name={`geometry${i}_rotationZInner`}
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

        <Form.Item label="Inner Label">
          <Tooltip
            title="The phase label for the current geometry"
            placement="bottomLeft"
          >
            <Form.Item
              name={`geometry${i}_labelInner`}
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

export { EllipsoidShellInput };
