import React from "react";
import { Row, Col, Button, Select, Divider, Switch } from "antd";
import { Viz3DContext, Viz3DActionType } from "../contexts/Viz3DContext";

const ipcRenderer = window.require("electron").ipcRenderer;

function arrayUnique(array: string[]) {
  var a = array.concat();
  for (var i = 0; i < a.length; ++i) {
    for (var j = i + 1; j < a.length; ++j) {
      if (a[i] === a[j]) a.splice(j--, 1);
    }
  }

  return a;
}

interface VTKViewControlState {
  fileList: string[];
  fileLoc: string;
  fileSelected: string;
  componentSelected: string;
  componentCount: number;
}

class VTKViewControl extends React.Component<
  { hideGIF: boolean },
  VTKViewControlState
> {
  static contextType = Viz3DContext;
  declare context: React.ContextType<typeof Viz3DContext>;

  state: VTKViewControlState;

  constructor(props: { hideGIF: boolean }) {
    super(props);
    this.state = {
      fileList: [],
      fileLoc: "",
      fileSelected: "",
      componentSelected: "",
      componentCount: 0,
    };
  }

  onVisualize = () => {
    console.log(`visualize button clicked `);
    console.log("visualize file", this.state.fileSelected);
    console.log(this.context.state);
    this.context.dispatch({
      type: Viz3DActionType.Update,
      payload: {
        fileName: this.state.fileSelected,
        fileLoc: this.state.fileLoc,
        // fileContent: result,
        loadData: true,
      },
    });
    // ipcRenderer
    //   .invoke("readFile", this.state.fileLoc, this.state.fileSelected)
    //   .then((result: string) => {
    //     // console.log("file read", result);
    //     this.context.dispatch({
    //       type: Viz3DActionType.Update,
    //       payload: {
    //         fileName: this.state.fileSelected,
    //         fileLoc: this.state.fileLoc,
    //         // fileContent: result,
    //         fileChanged: true,
    //       },
    //     });
    //   });
  };

  onFileChange = (value: string) => {
    console.log(`selected file ${value}`);
    this.setState({ fileSelected: value });
    this.context.dispatch({
      type: Viz3DActionType.Update,
      payload: {
        fileChanged: true,
      },
    });
  };

  onComponentChange = (value: string) => {
    console.log(`selected component ${value}`);
    this.setState({ componentSelected: value });

    this.context.dispatch({
      type: Viz3DActionType.Update,
      payload: {
        componentChanged: true,
      },
    });

    console.log(this.context.dispatch);
  };

  componentDidMount() {
    ipcRenderer.on(
      "fileList",
      (event: Event, fileLoc: string, fileList: string[]) => {
        // console.log("fileList", fileLoc, fileList);
        // let newList = arrayUnique([...this.state.fileList, ...fileList]);
        let newList: string[] = [];
        newList = newList.concat(...fileList); //arrayUnique([...this.state.fileList, ...fileList]);
        if (newList !== this.state.fileList) {
          this.setState({
            fileLoc: fileLoc,
            fileList: newList,
          });
          this.context.dispatch({
            type: Viz3DActionType.Update,
            payload: {
              fileList: this.state.fileList,
              fileLoc: this.state.fileLoc,
            },
          });
        }
        // console.log("get file List from the main",this.state.fileList);
      }
    );
  }

  onSaveCurrent = () => {
    console.log(
      "VTKViewControl:onSaveCurrent:context:state",
      this.context.state
    );
    this.context.dispatch({
      type: Viz3DActionType.Update,
      payload: {
        exportScene: true,
      },
    });
  };

  onSaveGIF = () => {
    console.log("save image sequence to gif");
    this.context.dispatch({
      type: Viz3DActionType.Update,
      payload: {
        exportGIF: true,
      },
    });
  };

  render() {
    return (
      <>
        <h5 className="inline-block">3D visualization</h5>
        <Row className="visualization-control-row">
          <Select
            showSearch
            style={{ width: 200, marginRight: 10 }}
            placeholder="Select a file"
            optionFilterProp="children"
            onChange={this.onFileChange}
            filterOption={(input, option) =>
              String(option!.children)
                .toLowerCase()
                .indexOf(input.toLowerCase()) >= 0
            }
          >
            {this.state.fileList.map((file, index) => (
              <Select.Option value={file} key={index.toString()}>
                {file}
              </Select.Option>
            ))}
          </Select>
          <Button
            type="primary"
            onClick={this.onVisualize}
            style={{ width: 170 }}
          >
            Load data
          </Button>
        </Row>
        {!this.context.state.fileChanged &&
        this.context.state.fileName !== "" &&
        this.context.state.fileName !== undefined ? (
          <Row className="visualization-control-row">
            <Select
              showSearch
              style={{ width: 200, marginRight: 10 }}
              placeholder="Select a component"
              optionFilterProp="children"
              onChange={this.onComponentChange}
              // onFocus={this.onFocus}
              // onBlur={this.onBlur}
              // onSearch={this.onSearch}
              defaultValue={this.context.state.componentNames![0]}
              filterOption={(input, option) =>
                String(option!.children)
                  .toLowerCase()
                  .indexOf(input.toLowerCase()) >= 0
              }
            >
              {this.context.state.componentNames!.map((element, index) => (
                <Select.Option value={element} key={index.toString()}>
                  {element}
                </Select.Option>
              ))}
            </Select>
          </Row>
        ) : null}

        <Row className="visualization-control-row">
          <Button
            type="primary"
            onClick={this.onSaveCurrent}
            style={{ width: 200, marginRight: 10 }}
          >
            Save current scene
          </Button>
          {!this.props.hideGIF ? (
            <Button
              type="primary"
              onClick={this.onSaveGIF}
              style={{ width: 170 }}
            >
              Create GIF
            </Button>
          ) : null}
        </Row>
      </>
    );
  }
}

export { VTKViewControl };
