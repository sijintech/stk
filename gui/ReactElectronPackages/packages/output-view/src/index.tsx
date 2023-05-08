import React, { useContext, useEffect } from "react";
import { Col, Row } from "antd";
import "./index.less";

import { VTKView } from "./components/VTKView";
import { ConsoleView } from "./components/ConsoleView";
import { VTKViewControl } from "./components/VTKViewControl";

import { Viz3DProvider } from "./contexts/Viz3DContext";
import { Viz3DContext, Viz3DActionType } from "./contexts/Viz3DContext";

const OutputView: React.FC = () => {
  const { state, dispatch } = useContext(Viz3DContext);

  useEffect(() => {
    if (state.initialSetup) {
      dispatch({
        type: Viz3DActionType.Update,
        payload: {
          initialSetup: false,
        },
      });
    }
  });

  return (
    <Viz3DProvider>
      <Col className="output">
        <Row className="output-row">
          <Col className="output-panel">
            <VTKView />
          </Col>
          <Col flex="400px" className="visualization-control-panel">
            <VTKViewControl hideGIF={true} />
          </Col>
        </Row>
        <Row className="stdoutput-row">
          <ConsoleView />
        </Row>
      </Col>
    </Viz3DProvider>
  );
};

export { OutputView };
