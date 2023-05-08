import React from "react";
import { Row, Col, Button, Select, Divider, Switch } from "antd";
import { connect } from "dva";
import { TreeSelect } from "antd";
const ipcRenderer = window.require("electron").ipcRenderer;

class ChartViewControl extends React.Component {
  constructor(props) {
    super(props);
    this.xaxisRef = React.createRef();
    this.state = {
      timeList: [],
      fileLoc: "",
      timeFileSelected: "",
      xValue: null,
      xList: [],
      yValue: [],
      yList: [],
    };
  }

  componentDidMount() {
    ipcRenderer.on("timeList", (event, fileLoc, timeList) => {
      let newTimeList = arrayUnique([...this.state.timeList, ...timeList]);
      if (newList !== this.state.fileList) {
        this.setState({
          fileLoc: fileLoc,
          timeList: newTimeList,
        });
        this.props.dispatch({
          type: "visualizationConfig/update",
          payload: {
            timeList: this.state.timeList,
            fileLoc: this.state.fileLoc,
          },
        });
      }
      // console.log("get file List from the main",this.state.fileList);
    });
  }
  formatTimeData = (input) => {
    let output = [];
    let temp = {};
    for (let index = 0; index < input.length; index++) {
      const element = input[index];
      temp = element;
      for (const key in element) {
        temp = {};
        // console.log("check",key,this.state.yValue,this.state.yValue.indexOf(key)!==-1);
        if (
          key !== this.state.xValue &&
          this.state.yValue.indexOf(key) !== -1
        ) {
          temp["xaxis"] = Number(element[this.state.xValue]);
          temp["value"] = Number(element[key]);
          temp["category"] = key;
          output.push(temp);
        }
      }
    }
    // console.log(output);
    return output;
  };

  onTimeVisualize = () => {
    ipcRenderer
      .invoke(
        "readCSV",
        path.join(this.state.fileLoc, this.state.timeFileSelected)
      )
      .then((result) => {
        console.log(result);
        let temp = [];
        let temp1 = [];
        for (const key in result[0]) {
          // if(key!=='kt'){
          temp.push(key);
          temp1.push({ title: key, value: key, key: key });
          // }
        }
        this.setState({ yValue: temp, yList: temp1 });
        this.setState({ xValue: "kt" });
        this.props.dispatch({
          type: "visualizationConfig/update",
          payload: {
            timeFileName: this.state.timeFileSelected,
            fileLoc: this.state.fileLoc,
            timeFileContent: this.formatTimeData(result),
            timeFileOriginal: result,
            timeFileChanged: true,
          },
        });
        console.log("ther eferecne curent", this.xaxisRef.current);
        console.log("this state", this.state.xValue);
      });
  };

  onTimeFileChange = (value) => {
    console.log(`selected file ${value}`);
    this.setState({ timeFileSelected: value });
    this.props.dispatch({
      type: "visualizationConfig/update",
      payload: {
        timeFileName: value,
        timeFileChanged: true,
      },
    });
  };

  onTimeSaveCurrent = () => {
    console.log("save current time scenee");
    this.props.dispatch({
      type: "visualizationConfig/update",
      payload: {
        exportTimeScene: true,
      },
    });
    console.log("save current time scene", this.props.visualizationConfig);
  };

  onTimeToggle = (value) => {
    console.log("Toggle the 2D", value);
    this.props.dispatch({
      type: "visualizationConfig/update",
      payload: {
        visualizationTime: value,
      },
    });
    console.log("the ", this.props.visualizationConfig);
    ipcRenderer.invoke("nudgeWindow");
  };

  onXFieldChange = (value) => {
    console.log("onChange X ", value);
    this.setState({ xValue: value }, () => {
      this.props.dispatch({
        type: "visualizationConfig/update",
        payload: {
          timeFileContent: this.formatTimeData(
            this.props.visualizationConfig.timeFileOriginal
          ),
        },
      });
    });
    console.log(
      "ther eferecne curent of x field change",
      this.xaxisRef.current
    );
  };

  onYFieldChange = (value) => {
    console.log("onChange Y", value);
    this.setState({ yValue: value }, () => {
      this.props.dispatch({
        type: "visualizationConfig/update",
        payload: {
          timeFileContent: this.formatTimeData(
            this.props.visualizationConfig.timeFileOriginal
          ),
        },
      });
    });
  };

  render() {
    const treeData = this.state.yList;

    const tProps = {
      treeData,
      value: this.state.yValue,
      onChange: this.onYFieldChange,
      treeCheckable: true,
      placeholder: "Please select the column to plot",
      style: {
        width: "100%",
        // width: 200, marginRight: 10
      },
    };

    return (
      <>
        <Row>
          <Switch
            className="toggle-switch"
            checkedChildren="Time on"
            unCheckedChildren="Time off"
            onChange={this.onTimeToggle}
          />
          <h5>Time Series visualization</h5>
        </Row>
        <Row className="visualization-control-row">
          <Select
            showSearch
            style={{ width: 200, marginRight: 10 }}
            placeholder="Select a file"
            optionFilterProp="children"
            onChange={this.onTimeFileChange}
            // onFocus={this.onFocus}
            // onBlur={this.onBlur}
            // onSearch={this.onSearch}
            filterOption={(input, option) =>
              option.children.toLowerCase().indexOf(input.toLowerCase()) >= 0
            }
          >
            {this.state.timeList.map((file, index) => (
              <Option value={file} key={index}>
                {file}
              </Option>
            ))}
          </Select>
          <Button
            type="primary"
            onClick={this.onTimeVisualize}
            style={{ width: 170 }}
          >
            Load data
          </Button>
        </Row>
        <Row>
          <Select
            showSearch
            style={{ width: "100%", marginBottom: 10 }}
            placeholder="Select the data column for x axis"
            notFoundContent="Select the data column for x axis"
            optionFilterProp="children"
            onChange={this.onXFieldChange}
            // onFocus={this.onFocus}
            // onBlur={this.onBlur}
            // onSearch={this.onSearch}
            value={this.state.xValue}
            ref={this.xaxisRef}
            filterOption={(input, option) =>
              option.children.toLowerCase().indexOf(input.toLowerCase()) >= 0
            }
          >
            {this.state.yValue.map((file, index) => (
              <Option value={file} key={index}>
                {file}
              </Option>
            ))}
          </Select>
          <TreeSelect {...tProps} />
          <Button
            type="primary"
            onClick={this.onTimeUpdate}
            style={{ width: 170 }}
          >
            Update visualization
          </Button>
        </Row>
        <Button
          type="primary"
          onClick={this.onTimeSaveCurrent}
          style={{ width: 170, marginLeft: 210 }}
        >
          Save current scene
        </Button>
      </>
    );
  }
}

function mapStateToProps({ visualizationConfig }) {
  return { visualizationConfig };
}

export default connect(mapStateToProps, null, null, { withRef: true })(
  ChartViewControl
);
