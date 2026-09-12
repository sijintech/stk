import {useEffect,useRef,useState} from 'react';
import '@kitware/vtk.js/Rendering/Profiles/Geometry';
import vtkGenericRenderWindow from '@kitware/vtk.js/Rendering/Misc/GenericRenderWindow';
import vtkPolyData from '@kitware/vtk.js/Common/DataModel/PolyData';
import vtkMapper from '@kitware/vtk.js/Rendering/Core/Mapper';
import vtkActor from '@kitware/vtk.js/Rendering/Core/Actor';
import vtkDataArray from '@kitware/vtk.js/Common/Core/DataArray';
import vtkColorTransferFunction from '@kitware/vtk.js/Rendering/Core/ColorTransferFunction';
import vtkCellPicker from '@kitware/vtk.js/Rendering/Core/CellPicker';
import type {Json} from './api';

export default function Viewer({scene,onPick}:{scene:Json|null,onPick:(p:number[])=>void}){
  const ref=useRef<HTMLDivElement>(null),pick=useRef(onPick);pick.current=onPick;
  const [error,setError]=useState('');
  useEffect(()=>{
    if(!ref.current||!scene)return;
    let cleanup=()=>{};
    try{
      const {mesh,manifest}=scene;
      if(manifest.version!==1||mesh.positions.length!==mesh.values.length||mesh.indices.some((i:number)=>i<0||i>=mesh.positions.length))throw new Error('科学视图格式无效');
      const view=vtkGenericRenderWindow.newInstance({background:[.086,.098,.129]});view.setContainer(ref.current);
      const poly=vtkPolyData.newInstance();poly.getPoints().setData(new Float32Array(mesh.positions.flat()),3);
      const cells=new Uint32Array(mesh.indices.length/3*4);
      for(let i=0,j=0;i<mesh.indices.length;i+=3,j+=4)cells.set([3,...mesh.indices.slice(i,i+3)],j);
      poly.getPolys().setData(cells);
      poly.getPointData().setScalars(vtkDataArray.newInstance({name:'field',values:new Float32Array(mesh.values),numberOfComponents:1}));
      const lut=vtkColorTransferFunction.newInstance();const [min,max]=manifest.value_range;const high=max>min?max:min+1;
      lut.addRGBPoint(min,.12,.22,.55);lut.addRGBPoint((min+high)/2,.2,.72,.65);lut.addRGBPoint(high,.95,.82,.2);
      const mapper=vtkMapper.newInstance();mapper.setInputData(poly);mapper.setLookupTable(lut);mapper.setScalarRange(min,high);
      const actor=vtkActor.newInstance();actor.setMapper(mapper);actor.getProperty().setLighting(false);
      const renderer=view.getRenderer();renderer.addActor(actor);renderer.resetCamera();view.resize();view.getRenderWindow().render();
      const picker=vtkCellPicker.newInstance();picker.setPickFromList(true);picker.addPickList(actor);
      const subscription=view.getInteractor().onLeftButtonPress((event:any)=>{
        picker.pick([event.position.x,event.position.y,0],renderer);
        if(picker.getCellId()>=0)pick.current(picker.getPickPosition().map((v:number,i:number)=>v+manifest.render_origin[i]));
      });
      const observer=new ResizeObserver(()=>view.resize());observer.observe(ref.current);
      cleanup=()=>{observer.disconnect();subscription.unsubscribe();picker.delete();view.delete();actor.delete();mapper.delete();poly.delete();lut.delete();};setError('');
    }catch(e){setError(String(e));}
    return ()=>cleanup();
  },[scene]);
  return <div className="viewport" ref={ref} aria-label="科学三维视图">{!scene&&<div className="empty"><span className="orbit">◎</span><h2>让计算结果成为可探索的空间</h2><p>选择已完成任务的结果文件，加载切片、等值面或向量场。</p><small>原始数据保留在执行节点，当前设备负责三维交互。</small></div>}{error&&<p role="alert">{error}</p>}</div>;
}
