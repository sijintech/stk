use std::sync::Arc;
use wgpu::util::DeviceExt;
use crate::scene::{Scene, color};

#[repr(C)]
#[derive(Clone, Copy, bytemuck::Pod, bytemuck::Zeroable)]
struct Vertex { position: [f32;3], color: [f32;3] }

pub struct SceneRenderer {
    pipeline: wgpu::RenderPipeline,
    uniform: wgpu::Buffer,
    bindings: wgpu::BindGroup,
    vertices: wgpu::Buffer,
    indices: wgpu::Buffer,
    count: u32,
    revision: u64,
}

impl SceneRenderer {
    pub fn new(device: &wgpu::Device, format: wgpu::TextureFormat) -> Self {
        let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
            label:Some("STK scientific surface"),source:wgpu::ShaderSource::Wgsl(include_str!("surface.wgsl").into())});
        let pipeline = device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
            label:Some("STK scientific surface"),layout:None,
            vertex:wgpu::VertexState {module:&shader,entry_point:Some("vs_main"),compilation_options:Default::default(),
                buffers:&[Some(wgpu::VertexBufferLayout {array_stride:24,step_mode:wgpu::VertexStepMode::Vertex,
                    attributes:&wgpu::vertex_attr_array![0=>Float32x3,1=>Float32x3]})]},
            fragment:Some(wgpu::FragmentState {module:&shader,entry_point:Some("fs_main"),compilation_options:Default::default(),targets:&[Some(format.into())]}),
            primitive:wgpu::PrimitiveState {cull_mode:None,..Default::default()},
            depth_stencil:Some(wgpu::DepthStencilState {format:wgpu::TextureFormat::Depth32Float,
                depth_write_enabled:Some(true),depth_compare:Some(wgpu::CompareFunction::LessEqual),stencil:Default::default(),bias:Default::default()}),
            multisample:Default::default(),multiview_mask:None,cache:None });
        let uniform=device.create_buffer_init(&wgpu::util::BufferInitDescriptor {label:Some("camera"),
            contents:bytemuck::cast_slice(&glam::Mat4::IDENTITY.to_cols_array()),usage:wgpu::BufferUsages::UNIFORM|wgpu::BufferUsages::COPY_DST});
        let bindings=device.create_bind_group(&wgpu::BindGroupDescriptor {label:Some("camera"),layout:&pipeline.get_bind_group_layout(0),
            entries:&[wgpu::BindGroupEntry {binding:0,resource:uniform.as_entire_binding()}]});
        let vertices=device.create_buffer_init(&wgpu::util::BufferInitDescriptor {label:None,contents:&[0;24],usage:wgpu::BufferUsages::VERTEX});
        let indices=device.create_buffer_init(&wgpu::util::BufferInitDescriptor {label:None,contents:&[0;4],usage:wgpu::BufferUsages::INDEX});
        Self {pipeline,uniform,bindings,vertices,indices,count:0,revision:u64::MAX}
    }

    pub fn prepare(&mut self, device:&wgpu::Device, queue:&wgpu::Queue, scene:&Scene, matrix:glam::Mat4, revision:u64) {
        if self.revision!=revision {
            let data:Vec<Vertex>=scene.mesh.positions.iter().zip(&scene.mesh.values).map(|(p,v)| Vertex {
                position:p.map(|n| n as f32),color:color(*v,scene.manifest.value_range)}).collect();
            if !data.is_empty() && !scene.mesh.indices.is_empty() {
                self.vertices=device.create_buffer_init(&wgpu::util::BufferInitDescriptor {label:Some("scientific points"),contents:bytemuck::cast_slice(&data),usage:wgpu::BufferUsages::VERTEX});
                self.indices=device.create_buffer_init(&wgpu::util::BufferInitDescriptor {label:Some("triangles"),contents:bytemuck::cast_slice(&scene.mesh.indices),usage:wgpu::BufferUsages::INDEX});
            }
            self.count=scene.mesh.indices.len() as u32;
            self.revision=revision;
        }
        queue.write_buffer(&self.uniform,0,bytemuck::cast_slice(&matrix.to_cols_array()));
    }

    pub fn paint(&self, pass:&mut wgpu::RenderPass<'_>) {
        if self.count==0 {return;}
        pass.set_pipeline(&self.pipeline);
        pass.set_bind_group(0,&self.bindings,&[]);
        pass.set_vertex_buffer(0,self.vertices.slice(..));
        pass.set_index_buffer(self.indices.slice(..),wgpu::IndexFormat::Uint32);
        pass.draw_indexed(0..self.count,0,0..1);
    }
}

pub struct SceneCallback {pub scene:Arc<Scene>,pub matrix:glam::Mat4,pub revision:u64}
impl egui_wgpu::CallbackTrait for SceneCallback {
    fn prepare(&self,device:&wgpu::Device,queue:&wgpu::Queue,_:&egui_wgpu::ScreenDescriptor,
        _:&mut wgpu::CommandEncoder,resources:&mut egui_wgpu::CallbackResources)->Vec<wgpu::CommandBuffer> {
        if let Some(renderer)=resources.get_mut::<SceneRenderer>() {renderer.prepare(device,queue,&self.scene,self.matrix,self.revision);}
        vec![]
    }
    fn paint(&self,_:egui::PaintCallbackInfo,pass:&mut wgpu::RenderPass<'static>,resources:&egui_wgpu::CallbackResources) {
        if let Some(renderer)=resources.get::<SceneRenderer>() {renderer.paint(pass);}
    }
}
