import { useEffect, useState } from "react";
// import { Input, Form, Tooltip, Row } from "antd";
// import { connect } from "dva";
import { Register } from "./components/register";
import { Preferences } from "./components/preferences";

const ipcRenderer = window.require("electron").ipcRenderer;

const Modal: React.FC = () => {
  const [isRegisterOpen, setIsRegisterOpen] = useState(false);
  const [isPreferencesOpen, setIsPreferencesOpen] = useState(false);

  useEffect(() => {
    console.log("Load the modal");
    ipcRenderer.on("preferencesOpen", (event: Event, message: string) => {
      console.log("preferences open", message);
      setIsPreferencesOpen(true);
    });

    ipcRenderer.on("registerOpen", (event: Event, message: string) => {
      console.log("register open", message);
      setIsRegisterOpen(true);
    });
  }, []);

  return (
    <>
      <Register
        show={isRegisterOpen}
        onClose={() => {
          setIsRegisterOpen(false);
        }}
      />

      <Preferences
        show={isPreferencesOpen}
        onClose={() => {
          setIsPreferencesOpen(false);
        }}
      />
    </>
  );
};

export { Modal };
