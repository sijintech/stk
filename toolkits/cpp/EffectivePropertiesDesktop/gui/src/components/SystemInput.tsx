import React from "react";
import { Form, Tooltip, Select, Switch, FormInstance } from "antd";
// import {DielectricInput, DielectricInputImport} from "../dielectricInput/dielectricInput";
// import ElectricalInput from "../electricalInput/electricalInput";
// import MagneticInput from "../magneticInput/magneticInput";
// import ThermalInput from "../thermalInput/thermalInput";
// import DiffusionInput from "../diffusionInput/diffusionInput";
// import ElasticInput from "../elasticInput/elasticInput";
// import PiezoelectricInput from "../piezoelectricInput/piezoelectricInput";
// import PiezomagneticInput from "../piezomagneticInput/piezomagneticInput";
// import { getKeyThenIncreaseKey } from "antd/lib/message";
// import MagnetoelectricInput from "../magnetoelectricInput/magnetoelectricInput";

import { System } from "./System";
import type { SystemType, SystemData as SystemInputData } from "./typings";
import { defaultTensorType } from "@mupro/typings/TensorInput";
import "./SystemInput.less";
import { marginBottom } from "@mupro/typings/Constants";
import {
  DielectricRefTensorList,
  DielectricTensorList,
  ElectricalRefTensorList,
  ElectricalTensorList,
  MagneticRefTensorList,
  MagneticTensorList,
  ElasticRefTensorList,
  ElasticTensorList,
  ThermalRefTensorList,
  ThermalTensorList,
  PiezoelectricRefTensorList,
  PiezoelectricTensorList,
  PiezomagneticRefTensorList,
  PiezomagneticTensorList,
  DiffusionTensorList,
  DiffusionRefTensorList,
} from "./typings";
import type { TensorType } from "@mupro/typings/TensorInput";
const { Option } = Select;

// type SystemInputImport = DielectricInputImport;
// type SystemInputExport = DielectricInputExport;
interface SystemInputState {
  systemType: SystemType;
  systemDistribution: boolean;
}

class SystemInput extends React.Component<{}, SystemInputState> {
  formRef: React.RefObject<FormInstance>;
  systemRef: React.RefObject<System>;
  // dielectricRef: React.RefObject<DielectricInput>
  // electricalRef: React.RefObject<ElectricalInput>
  // magneticRef: React.RefObject<MagneticInput>
  // thermalRef: React.RefObject<ThermalInput>
  // diffusionRef: React.RefObject<DiffusionInput>
  // elasticRef: React.RefObject<ElasticInput>
  // piezoelectricRef: React.RefObject<PiezoelectricInput>
  // piezomagneticRef: React.RefObject<PiezomagneticInput>
  systemName: {
    empty: "";
    dielectric: string;
    electrical: string;
    magnetic: string;
    thermal: string;
    diffusion: string;
    elastic: string;
    piezoelectric: string;
    piezomagnetic: string;
  };
  refTensorList: {
    empty: TensorType[];
    dielectric: TensorType[];
    electrical: TensorType[];
    magnetic: TensorType[];
    thermal: TensorType[];
    diffusion: TensorType[];
    elastic: TensorType[];
    piezoelectric: TensorType[];
    piezomagnetic: TensorType[];
  };

  tensorList: {
    empty: TensorType[];
    dielectric: TensorType[];
    electrical: TensorType[];
    magnetic: TensorType[];
    thermal: TensorType[];
    diffusion: TensorType[];
    elastic: TensorType[];
    piezoelectric: TensorType[];
    piezomagnetic: TensorType[];
  };

  constructor(props: {}) {
    super(props);
    this.state = {
      systemType: "empty",
      systemDistribution: false,
    };
    // this.dielectricRef = React.createRef()
    // this.electricRef = React.createRef()
    // this.magneticRef = React.createRef()
    // this.thermalRef = React.createRef()
    // this.diffusionRef = React.createRef()
    // this.elasticRef = React.createRef()
    // this.piezoelectricRef = React.createRef()
    // this.piezomagneticRef = React.createRef()
    this.formRef = React.createRef();
    this.systemRef = React.createRef();
    this.systemName = {
      empty: "",
      dielectric: "Dielectric System",
      electrical: "Electrical Conduction System",
      magnetic: "Magnetic System",
      thermal: "Thermal Conduction System",
      diffusion: "Diffusion System",
      elastic: "Elastic System",
      piezoelectric: "Piezoelectric System",
      piezomagnetic: "Piezomagnetic System",
    };
    this.refTensorList = {
      empty: [defaultTensorType],
      dielectric: DielectricRefTensorList,
      electrical: ElectricalRefTensorList,
      magnetic: MagneticRefTensorList,
      thermal: ThermalRefTensorList,
      diffusion: DiffusionRefTensorList,
      elastic: ElasticRefTensorList,
      piezoelectric: PiezoelectricRefTensorList,
      piezomagnetic: PiezomagneticRefTensorList,
    };
    this.tensorList = {
      empty: [defaultTensorType],
      dielectric: DielectricTensorList,
      electrical: ElectricalTensorList,
      magnetic: MagneticTensorList,
      thermal: ThermalTensorList,
      diffusion: DiffusionTensorList,
      elastic: ElasticTensorList,
      piezoelectric: PiezoelectricTensorList,
      piezomagnetic: PiezomagneticTensorList,
    };
  }

  // getCurrentSystemRef = () => {
  //   switch (this.state.systemType) {
  //     case 'dielectric':
  //       return this.dielectricRef;
  //     case 'electrical':
  //       return this.electricalRef;
  //     case 'magnetic':
  //       return this.magneticRef;
  //     case 'thermal':
  //       return this.thermalRef;
  //     case 'diffusion':
  //       return this.diffusionRef;
  //     case 'elastic':
  //       return this.elasticRef;
  //     case 'piezoelectric':
  //       return this.piezoelectricRef;
  //     case 'piezomagnetic':
  //       return this.piezomagneticRef;
  //     default:
  //       return null
  //   }
  // }
  onFinish = (): SystemInputData => {
    console.log("the on finish of System input");
    // let values = this.formRef.current!.getFieldsValue(true);

    // return this.getCurrentSystemRef()!.current.onFinish(values);
    return this.systemRef!.current!.onFinish();
    // let distri = 1;
    // if (values["systemDistribution"] === false) {
    //   distri = 0;
    // }
    // return {
    //   system: {
    //     type: values["systemType"],
    //     distribution: distri,
    //     ...sys,
    //   },
    // };
  };

  onImport = (system: SystemInputData) => {
    console.log("import from system input", system);
    let distri = true;
    if (system.distribution === "0") {
      distri = false;
    }
    console.log("distri", distri);
    console.log("system", system);
    // if (distri!=this.state.systemDistribution) {
    //   onDistributionToggle()
    // }
    this.setState(
      {
        systemType: system.type.trim() as SystemType,
        systemDistribution: distri,
      },
      () => {
        this.formRef.current!.setFieldsValue({
          systemType: system.type.trim(),
          systemDistribution: distri,
        });
        this.systemRef.current!.onImport(system);
      }
    );
  };

  onSelectSystemType = (value: SystemType) => {
    console.log("the system type changed ", value);
    this.setState({ systemType: value });
  };

  onDistributionToggle = (value: boolean) => {
    console.log("Toggle the distribution", value);
    this.setState({ systemDistribution: value });
  };

  render() {
    const formstyle = {
      labelCol: { span: 8 },
      wrapperCol: { span: 16 },
      style: { width: "100%" },
    };
    const formItemStyle = {
      style: { marginBottom: marginBottom },
    };
    return (
      <>
        <Form {...formstyle} ref={this.formRef}>
          <Tooltip title="Select the system type" placement="top">
            <Form.Item name="systemType" label="System Type" {...formItemStyle}>
              <Select
                placeholder="Select the system type"
                onChange={(value) => {
                  this.onSelectSystemType(value);
                }}
              >
                <Option value={"dielectric"}>Dielectric</Option>
                <Option value={"electrical"}>Electrical</Option>
                <Option value={"magnetic"}>Magnetic</Option>
                <Option value={"diffusion"}>Diffusion</Option>
                <Option value={"thermal"}>Thermal</Option>
                <Option value={"elastic"}>Elastic</Option>
                <Option value={"piezoelectric"}>Piezoelectric</Option>
                <Option value={"piezomagnetic"}>Piezomagnetic</Option>
                {/* <Option value={"magnetoelectric"}>Magnetoelectric</Option> */}
              </Select>
            </Form.Item>
          </Tooltip>
          <Form.Item
            name="systemDistribution"
            label="Distribution"
            valuePropName="checked"
            {...formItemStyle}
          >
            <Switch
              className="toggle-switch"
              checkedChildren="Calculate"
              unCheckedChildren="Don't Calculate"
              style={{ width: 150, margin: 0 }}
              onChange={this.onDistributionToggle}
            />
          </Form.Item>
        </Form>

        <System
          name={this.systemName[this.state.systemType]}
          type={this.state.systemType}
          refTensorList={this.refTensorList[this.state.systemType]}
          tensorList={this.tensorList[this.state.systemType]}
          ref={this.systemRef}
          distribution={this.state.systemDistribution}
        />

        {/* {(() => {
          switch (this.state.systemType) {
            case 'dielectric':
              return <System name='Dielectric System' type='dielectric' refTensorList={DielectricRefTensorList} tensorList={DielectricTensorList} ref={this.dielectricRef} distribution={this.state.systemDistribution} />
            case 'electrical':
              return <System name='Electrical Conduction System' type='electrical' refTensorList={ElectricalRefTensorList} tensorList={ElectricalTensorList} ref={this.electricalRef} />
            case 'magnetic':
              return <System name='Magnetic System' type='magnetic' refTensorList={MagneticRefTensorList} tensorList={MagneticTensorList} ref={this.magneticRef} />
            case 'thermal':
              return <System name='Thermal System' type='thermal' refTensorList={ThermalRefTensorList} tensorList={ThermalTensorList} ref={this.thermalRef} />
            case 'diffusion':
              return <System name='Diffusion System' type='diffusion' refTensorList={DiffusionRefTensorList} tensorList={DiffusionTensorList} ref={this.diffusionRef} />
            case 'elastic':
              return <System name='Elastic System' type='elastic' refTensorList={ElasticRefTensorList} tensorList={ElasticTensorList}
                ref={this.elasticRef}
              />
            case 'piezoelectric':
              return <System name='Piezoelectric System' type='piezoelectric' refTensorList={PiezoelectricRefTensorList} tensorList={PiezoelectricTensorList} ref={this.piezoelectricRef} />
            case 'piezomagnetic':
              return <System name='Piezomagnetic System' type='piezomagnetic' refTensorList={PiezomagneticRefTensorList} tensorList={PiezomagneticTensorList} ref={this.piezomagneticRef} />
            // case 'magnetoelectric'
            //   return <MagnetoelectricInput
            //     formRef={this.props.formRef}
            //     ref={this.systemRef}
            //   />
            default:
              return null
          }
        })()} */}
      </>
    );
  }
}

export { SystemInput };
