import React from "react";
import { Input, Form, Tooltip } from "antd";
import type { GeometryInputProps } from "./geometryInput";
import type { EllipsoidRandomInputData } from "@mupro/typings/GeometryInput";

class EllipsoidRandomInput extends React.Component<GeometryInputProps, {}> {
  onImport = (geometry: EllipsoidRandomInputData) => {
    if (!this.props.formRef.current) return;
    let i = this.props.index;
    console.log("onImport from the EllipsoidRandom", i, geometry);
    this.props.formRef.current.setFieldsValue({
      [`geometry${i}_count`]: geometry.count.trim(),
      [`geometry${i}_centerXMin`]: geometry.centerXMin.trim(),
      [`geometry${i}_centerXMax`]: geometry.centerXMax.trim(),
      [`geometry${i}_centerYMin`]: geometry.centerYMin.trim(),
      [`geometry${i}_centerYMax`]: geometry.centerYMax.trim(),
      [`geometry${i}_centerZMin`]: geometry.centerZMin.trim(),
      [`geometry${i}_centerZMax`]: geometry.centerZMax.trim(),
      [`geometry${i}_radiusXMin`]: geometry.radiusXMin.trim(),
      [`geometry${i}_radiusYMin`]: geometry.radiusYMin.trim(),
      [`geometry${i}_radiusZMin`]: geometry.radiusZMin.trim(),
      [`geometry${i}_radiusXMax`]: geometry.radiusXMax.trim(),
      [`geometry${i}_radiusYMax`]: geometry.radiusYMax.trim(),
      [`geometry${i}_radiusZMax`]: geometry.radiusZMax.trim(),
      [`geometry${i}_rotationXMin`]: geometry.rotationXMin.trim(),
      [`geometry${i}_rotationYMin`]: geometry.rotationYMin.trim(),
      [`geometry${i}_rotationZMin`]: geometry.rotationZMin.trim(),
      [`geometry${i}_rotationXMax`]: geometry.rotationXMax.trim(),
      [`geometry${i}_rotationYMax`]: geometry.rotationYMax.trim(),
      [`geometry${i}_rotationZMax`]: geometry.rotationZMax.trim(),
      [`geometry${i}_label`]: geometry.label.trim(),
      [`geometry${i}_matrixLabel`]: geometry.matrixLabel.trim(),
    });
  };

  onFinish = (values: any): EllipsoidRandomInputData => {
    let i = this.props.index;
    console.log("onFinish from the EllipsoidRandom", i, values);
    return {
      type: "ellipsoid_random",
      count: values[`geometry${i}_count`],
      centerXMin: values[`geometry${i}_centerXMin`],
      centerXMax: values[`geometry${i}_centerXMax`],
      centerYMin: values[`geometry${i}_centerYMin`],
      centerYMax: values[`geometry${i}_centerYMax`],
      centerZMin: values[`geometry${i}_centerZMin`],
      centerZMax: values[`geometry${i}_centerZMax`],
      radiusXMin: values[`geometry${i}_radiusXMin`],
      radiusXMax: values[`geometry${i}_radiusXMax`],
      radiusYMin: values[`geometry${i}_radiusYMin`],
      radiusYMax: values[`geometry${i}_radiusYMax`],
      radiusZMin: values[`geometry${i}_radiusZMin`],
      radiusZMax: values[`geometry${i}_radiusZMax`],
      rotationXMin: values[`geometry${i}_rotationXMin`],
      rotationXMax: values[`geometry${i}_rotationXMax`],
      rotationYMin: values[`geometry${i}_rotationYMin`],
      rotationYMax: values[`geometry${i}_rotationYMax`],
      rotationZMin: values[`geometry${i}_rotationZMin`],
      rotationZMax: values[`geometry${i}_rotationZMax`],
      label: values[`geometry${i}_label`],
      matrixLabel: values[`geometry${i}_matrixLabel`],
    };
  };

  render() {
    let i = this.props.index;
    return (
      <div>
        <Form.Item label="Count">
          <Tooltip
            title="The amount of ellipsoid to be created."
            placement="bottomLeft"
          >
            <Form.Item
              name={`geometry${i}_count`}
              noStyle
              rules={[
                {
                  required: true,
                  message: "The number of ellipsoid is required",
                },
              ]}
            >
              <Input style={{ width: "33%" }} placeholder="10" />
            </Form.Item>
          </Tooltip>
        </Form.Item>
        <Form.Item label="Center">
          <Tooltip
            title={`The region of the center point for geometry${i}. The six numbers are the  xmin, xmax, ymin, ymax, zmin, zmax.`}
            placement="bottomLeft"
          >
            <Input.Group compact>
              <Form.Item
                name={`geometry${i}_centerXMin`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "lower bound for center x coordinate is required",
                  },
                ]}
              >
                <Input style={{ width: "16.5%" }} placeholder="20" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_centerXMax`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "upper bound for center x coordinate is required",
                  },
                ]}
              >
                <Input style={{ width: "16.5%" }} placeholder="80" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_centerYMin`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "lower bound for center y coordinate is required",
                  },
                ]}
              >
                <Input style={{ width: "16.5%" }} placeholder="20" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_centerYMax`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "upper bound center y coordinate is required",
                  },
                ]}
              >
                <Input style={{ width: "16.5%" }} placeholder="80" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_centerZMin`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "lower bound center z coordinate is required",
                  },
                ]}
              >
                <Input style={{ width: "16.5%" }} placeholder="20" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_centerZMax`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "upper bound for center z coordinate is required",
                  },
                ]}
              >
                <Input style={{ width: "16.5%" }} placeholder="80" />
              </Form.Item>
            </Input.Group>
          </Tooltip>
        </Form.Item>

        <Form.Item label="Radius">
          <Tooltip
            title={`The range of radius for the geometry${i}. The six numbers are radius xmin, xmax, ymin, ymax, zmin, zmax.`}
            placement="bottomLeft"
          >
            <Input.Group compact>
              <Form.Item
                name={`geometry${i}_radiusXMin`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "lower bound for radius x component is required",
                  },
                ]}
              >
                <Input style={{ width: "16.5%" }} placeholder="5" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_radiusXMax`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "upper bound for radius x component is required",
                  },
                ]}
              >
                <Input style={{ width: "16.5%" }} placeholder="10" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_radiusYMin`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "lower bound for radius y component is required",
                  },
                ]}
              >
                <Input style={{ width: "16.5%" }} placeholder="5" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_radiusYMax`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "upper bound for radius y component is required",
                  },
                ]}
              >
                <Input style={{ width: "16.5%" }} placeholder="10" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_radiusZMin`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "lower bound for radius z component is required",
                  },
                ]}
              >
                <Input style={{ width: "16.5%" }} placeholder="5" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_radiusZMax`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "upper bound for radius z component is required",
                  },
                ]}
              >
                <Input style={{ width: "16.5%" }} placeholder="10" />
              </Form.Item>
            </Input.Group>
          </Tooltip>
        </Form.Item>

        <Form.Item label="Rotation">
          <Tooltip
            title={`The range of rotation along xyz axis for the geometry${i}. The six numbers are rotation along xmin, xmax, ymin, ymax, zmin, zmax. The sequence of rotation is xyz.`}
            placement="bottomLeft"
          >
            <Input.Group compact>
              <Form.Item
                name={`geometry${i}_rotationXMin`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "lower bound for rotation along x is required",
                  },
                ]}
              >
                <Input style={{ width: "16.5%" }} placeholder="0" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_rotationXMax`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "upper bound for rotation along x is required",
                  },
                ]}
              >
                <Input style={{ width: "16.5%" }} placeholder="0" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_rotationYMin`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "lower bound for rotation along y is required",
                  },
                ]}
              >
                <Input style={{ width: "16.5%" }} placeholder="0" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_rotationYMax`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "upper bound for rotation along y is required",
                  },
                ]}
              >
                <Input style={{ width: "16.5%" }} placeholder="0" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_rotationZMin`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "lower bound for rotation along z is required",
                  },
                ]}
              >
                <Input style={{ width: "16.5%" }} placeholder="0" />
              </Form.Item>
              <Form.Item
                name={`geometry${i}_rotationZMax`}
                noStyle
                rules={[
                  {
                    required: true,
                    message: "upper bound for rotation along z is required",
                  },
                ]}
              >
                <Input style={{ width: "16.5%" }} placeholder="0" />
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

export { EllipsoidRandomInput };
