import React from "react";
import { Tabs, Divider } from "antd";
// import PhaseInput from "../phaseInput/PhaseInput";
import { PhaseInput } from "@mupro/input-form/src/components/PhaseInput";
import type { PhaseInputData } from "@mupro/typings/PhaseInput";

import { ExternalFieldInput } from "./ExternalField";
import type { SystemType, SystemData, ExternalField } from "./typings";
import type { TensorType } from "@mupro/typings/TensorInput";
import { marginBottom } from "@mupro/typings/Constants";
const { TabPane } = Tabs;

interface SystemProps {
  name: string;
  type: SystemType;
  refTensorList: TensorType[];
  tensorList: TensorType[];
  distribution: boolean;
}

interface SystemState {
  phaseCount: number;
}

class System extends React.Component<SystemProps, SystemState> {
  phaseRefList: React.RefObject<PhaseInput>[];
  externalRef: React.RefObject<ExternalFieldInput>;
  phaseRefHomo: React.RefObject<PhaseInput>;

  constructor(props: SystemProps) {
    super(props);
    this.phaseRefList = [React.createRef()];
    this.externalRef = React.createRef();
    this.phaseRefHomo = React.createRef();
    this.state = {
      phaseCount: 1, // must have at least one phase
    };
  }

  onFinish = (): SystemData => {
    let solverRef = this.phaseRefHomo.current!.onFinish();
    let phaseList: PhaseInputData[] = [];
    for (var i = 0; i < this.state.phaseCount; i++) {
      phaseList.push(this.phaseRefList[i].current!.onFinish());
    }
    if (this.externalRef.current && this.props.distribution) {
      let extern = this.externalRef.current.onFinish();
      return {
        type: this.props.type,
        distribution: "1",
        external: extern,
        solver: {
          ref: solverRef,
        },
        material: {
          phase: phaseList,
        },
      };
    } else {
      return {
        type: this.props.type,
        distribution: "0",
        solver: {
          ref: solverRef,
        },
        material: {
          phase: phaseList,
        },
      };
    }
  };

  add = () => {
    // console.log("add new phase", this.props.tensor);
    this.setState({ phaseCount: this.state.phaseCount + 1 });
    this.phaseRefList.push(React.createRef());
  };

  remove = (targetKey: string) => {
    console.log("remove phase");
    if (this.state.phaseCount === 1) {
      console.log(
        "something wrong, shouldn't be able to remove when count is 1, there must always be one phase"
      );
    } else {
      this.setState({ phaseCount: this.state.phaseCount - 1 });
      this.phaseRefList.splice(Number(targetKey), 1);
    }
  };

  onEdit = (
    targetKey:
      | string
      | React.MouseEvent<Element, MouseEvent>
      | React.KeyboardEvent<Element>,
    action: "add" | "remove"
  ) => {
    if (action === "add") {
      this.add();
    } else {
      this.remove(targetKey as string);
    }
  };

  onImport = (system: SystemData) => {
    const matIn = system.material;
    console.log("System::onImport::system", system);
    if (this.props.distribution && system.external)
      this.externalRef.current!.onImport(system.external);

    this.phaseRefHomo.current!.onImport(system.solver.ref);

    for (let index = 0; index < matIn.phase.length; index++) {
      this.phaseRefList.push(React.createRef());
    }

    this.setState({ phaseCount: matIn.phase.length }, () => {
      console.log("The phase", matIn.phase);
      for (let index = 0; index < matIn.phase.length; index++) {
        this.phaseRefList[index].current!.onImport(
          system.material.phase[index]
        );
      }
    });
  };

  render() {
    const dividerStyle = {
      style: { marginTop: marginBottom, marginBottom: marginBottom },
    };
    if (this.props.type === "empty") {
      return;
    } else {
      return (
        <div>
          <Divider {...dividerStyle} />
          <h5>{this.props.name}</h5>

          {this.props.distribution ? (
            <ExternalFieldInput type={this.props.type} ref={this.externalRef} />
          ) : null}

          <Tabs
            defaultActiveKey="1"
            tabPosition="top"
            style={{
              // height: 70 + 250 * this.state.tensorList.length,
              maxWidth: 430,
              marginBottom: 0,
            }}
            size={"small"}
            type="editable-card"
            onEdit={this.onEdit}
          >
            <TabPane tab={`Phase-ref`} key="ref" forceRender={true}>
              <PhaseInput
                phaseIndex="ref"
                tensorList={this.props.refTensorList}
                ref={this.phaseRefHomo}
              />
            </TabPane>
            {[...Array(this.state.phaseCount).keys()].map((i) => (
              <TabPane tab={`Phase-${i}`} key={i} forceRender={true}>
                <PhaseInput
                  phaseIndex={String(i)}
                  tensorList={this.props.tensorList}
                  ref={this.phaseRefList[i]}
                />
              </TabPane>
            ))}
          </Tabs>
        </div>
      );
    }
  }
}

export { System };
export type { SystemType };
