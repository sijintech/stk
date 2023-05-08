import React from "react";
import { Row, Col, Form, Input, Button } from "antd";
// import "./modal.less";
const ipcRenderer = window.require("electron").ipcRenderer;
import { ModalProps } from "../modals";

const Register: React.FC<ModalProps> = ({ show, onClose }) => {
  const [form] = Form.useForm();

  const onFinish = (values: FormData) => {
    console.log("finish user register", values);
    ipcRenderer.invoke("writeSecret", values).then((result: string) => {
      console.log("write secret", result);
    });
    onClose();
  };

  // Render nothing if the "show" prop is false
  console.log("register modal", show);
  if (!show) {
    return null;
  } else {
    return (
      <div className="backdrop">
        <Col className="modal">
          <Row justify="space-around">
            <Form
              onFinish={onFinish}
              labelCol={{ span: 4 }}
              wrapperCol={{ span: 20 }}
              style={{ width: "100%", padding: "60px" }}
            >
              <Form.Item label="Secret Id" name="user_register">
                <Input style={{ width: "100%" }} placeholder="xxxxxxxxxx" />
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
                  Close
                </Button>
                <Button type="primary" htmlType="submit" style={{ width: 130 }}>
                  Register
                </Button>
              </Form.Item>
            </Form>
          </Row>
        </Col>
      </div>
    );
  }
};

export { Register };
