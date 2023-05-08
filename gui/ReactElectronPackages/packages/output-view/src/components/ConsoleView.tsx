import React from "react";
// import {
//   Row,
// } from "antd";
import "./ConsoleView.less";
// import { connect } from "dva";
// const ipcRenderer = window.require("electron").ipcRenderer;
const ipcRenderer = window.require("electron").ipcRenderer;

// const { TabPane } = Tabs;
// const { Option } = Select;

interface ConsoleViewState {
  consoleOutput: string[];
}

class ConsoleView extends React.Component<{}, ConsoleViewState> {
  state: ConsoleViewState;

  constructor(props: {}) {
    super(props);
    this.state = {
      consoleOutput: [],
    };
  }
  componentDidMount() {
    console.log("The stdoutput did mount");
    ipcRenderer.on("console", (event: Event, message: string[] | string) => {
      console.log(message);
      let messageList = this.state.consoleOutput.concat(message);
      // messageList.push(message);
      this.setState({ consoleOutput: messageList });
    });
  }
  render() {
    return (
      <div className="stdOutput-panel">
        {this.state.consoleOutput.map((out, index) => (
          <p className="console-output" key={index}>
            {out}
          </p>
        ))}
      </div>
    );
  }
}

export { ConsoleView };
