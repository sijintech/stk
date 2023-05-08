import React, { useEffect, useState } from "react";
import { Row, Col, Form, Input, Button, Checkbox } from "antd";
// import "./modal.less";
// import { connect } from "dva";
import { PreferenceValue } from "@mupro/main-process/src/main-process";
const ipcRenderer = window.require("electron").ipcRenderer;
import { ModalProps } from "../modals";
import "./preferences.less";

const layout = {
  labelCol: { span: 4 },
  wrapperCol: { span: 20 },
};

const Preferences: React.FC<ModalProps> = ({ show, onClose }) => {
  // const [show, setShow] = useState(props.show);
  const [form] = Form.useForm();
  useEffect(() => {
    console.log("componeng will update", show);
    if (show) {
      ipcRenderer.invoke("loadPreferences").then((result: PreferenceValue) => {
        console.log("preferences ", result);
        console.log("prefernces", form);
        if (typeof result == "undefined") {
          form.setFieldsValue({
            hide_basic: false,
            hide_material: false,
            hide_structure: false,
          });
        } else {
          form.setFieldsValue({
            hide_basic: result.hide_basic ? true : false,
            hide_material: result.hide_material ? true : false,
            hide_structure: result.hide_structure ? true : false,
          });
        }
      });
    }
  });

  const onFinish = (values: FormData) => {
    console.log("finish user preferences", values);
    ipcRenderer.invoke("writePreferences", values).then((result: number) => {
      console.log("write preferences", result);
    });
    onClose();
  };

  console.log("preferences modal", show);
  // Render nothing if the "show" prop is false
  if (!show) {
    return null;
  } else {
    return (
      <div className="backdrop">
        <Col className="preferences-modal">
          <Row justify="space-around">
            <Form
              form={form}
              onFinish={onFinish}
              {...layout}
              style={{ width: "100%", padding: "60px" }}
            >
              <Form.Item name="hide_basic" valuePropName="checked">
                <Checkbox>Hide basic section</Checkbox>
              </Form.Item>
              <Form.Item name="hide_material" valuePropName="checked">
                <Checkbox>Hide material section</Checkbox>
              </Form.Item>
              <Form.Item name="hide_structure" valuePropName="checked">
                <Checkbox>Hide structure section</Checkbox>
              </Form.Item>
              <Form.Item label=" " colon={false} style={{ textAlign: "right" }}>
                <Button
                  type="primary"
                  // htmlType="submit"
                  onClick={onClose}
                  style={{
                    marginRight: 5,
                    marginLeft: "auto",
                    width: 140,
                  }}
                >
                  Cancel
                </Button>
                <Button type="primary" htmlType="submit" style={{ width: 130 }}>
                  Save
                </Button>
              </Form.Item>
            </Form>
          </Row>
        </Col>
      </div>
    );
  }
};

export { Preferences };
