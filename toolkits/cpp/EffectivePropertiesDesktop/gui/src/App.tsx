import { Button } from "antd";
import React from "react";
// import 'antd/dist/antd.css';
import { Modal } from "@mupro/modals/src";
import { ParameterInput } from "./components/parameterInput";
// import { Output } from './components/output';
import { OutputView } from "@mupro/output-view/src";
import "./App.css";
const App: React.FC = () => (
  <div className="App-header">
    <Modal />
    <ParameterInput />
    <OutputView />
    {/* <Button type="primary">Primary Button</Button>
    <Button>Default Button</Button>
    <Button type="dashed">Dashed Button</Button>
    <br />
    <Button type="text">Text Button</Button>
    <Button type="link">Link Button</Button> */}
  </div>
);

export default App;
