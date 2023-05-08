import React, { Component } from "react";
import "./ChartView.less";
import { Line } from "@ant-design/charts";

import { connect } from "dva";
// import { SSL_OP_SSLEAY_080_CLIENT_DH_BUG } from 'constants';
// const path = require("path");
const ipcRenderer = window.require("electron").ipcRenderer;

// import vtkFullScreenRenderWindow from 'vtk.js/Sources/Rendering/Misc/GenericRenderWindow';

// const useMountEffect = (fun) => useEffect(fun, [])

class ChartView extends Component {
  constructor(props) {
    super(props);
    this.ref = React.createRef();
  }

  componentDidMount() {}
  componentDidUpdate(prevProps) {
    if (this.props.visualizationConfig.exportTimeScene) {
      console.log("somethign before", this.ref);
      ipcRenderer.invoke(
        "writeFile",
        this.ref.current.toDataURL().replace(/^data:image\/\w+;base64,/, "")
      );
      console.log("somethign after");
      this.props.dispatch({
        type: "visualizationConfig/update",
        payload: {
          exportTimeScene: false,
        },
      });
    }
  }

  render() {
    let data = this.props.visualizationConfig.timeFileContent;
    const config = {
      data,
      padding: "auto",
      xField: "freq",
      yField: "value",
      seriesField: "category",
      xAxis: { tickCount: 10 },
      slider: {
        start: 0.1,
        end: 0.5,
      },
    };

    return (
      <div className="TimeView">
        <Line {...config} chartRef={this.ref} />
      </div>
    );
  }
}

function mapStateToProps({ visualizationConfig }) {
  return { visualizationConfig };
}

export default connect(mapStateToProps, null, null, { withRef: true })(
  ChartView
);
