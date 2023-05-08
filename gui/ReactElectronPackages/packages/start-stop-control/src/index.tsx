import React from "react";
import { Button, Row } from "antd";
// import "./structureInput.less";
const ipcRenderer = window.require("electron").ipcRenderer;

interface StartStopControlProps {
  fileLocation: string;
}
class StartStopControl extends React.Component<StartStopControlProps, {}> {
  constructor(props: StartStopControlProps) {
    super(props);
    // window.startStopControl = this;
  }

  // onFinish = (values) => {
  //   console.log("The system dimension input",this.props.simConfig,values['nx'])
  // }

  startSimulation = () => {
    console.log("Start the simulation", this.props.fileLocation);

    ipcRenderer
      .invoke("startSimulation", this.props.fileLocation)
      .then((result: string) => {
        console.log("this is the return result of start simulation", result);
      });
  };

  killSimulation = () => {
    console.log("Kill the simulation");
    ipcRenderer.invoke("killSimulation").then((result: string) => {
      console.log("kill the simulation", result);
    });
  };

  render() {
    return (
      <Row>
        <Button
          type="primary"
          style={{ marginRight: 5, marginLeft: "auto", width: 140 }}
          onClick={this.startSimulation}
        >
          Start simulation
        </Button>
        <Button
          type="primary"
          danger
          onClick={this.killSimulation}
          style={{ width: 130 }}
        >
          Stop simulation
        </Button>
      </Row>
    );
  }
}

// function mapStateToProps({ simConfig }) {
//     return { simConfig };
//   }
export { StartStopControl };
