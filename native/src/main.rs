use stk_workbench::{render::SceneRenderer,workbench::Workbench};

struct Desktop(Workbench);
impl eframe::App for Desktop {
    fn ui(&mut self,ui:&mut egui::Ui,_:&mut eframe::Frame) {self.0.ui(ui);}
}

fn main()->eframe::Result {
    let url=std::env::var("STK_CONTROL_URL").unwrap_or_else(|_|"http://127.0.0.1:8790".into());
    let token=std::env::var("STK_CONTROL_TOKEN").unwrap_or_default();
    let options=eframe::NativeOptions {renderer:eframe::Renderer::Wgpu,depth_buffer:32,multisampling:0,
        viewport:egui::ViewportBuilder::default().with_inner_size([1440.,900.]).with_min_inner_size([960.,640.]),..Default::default()};
    eframe::run_native("STK 科学工作台",options,Box::new(move |cc| {
        let render=cc.wgpu_render_state.as_ref().ok_or("wgpu renderer unavailable")?;
        render.renderer.write().callback_resources.insert(SceneRenderer::new(&render.device,render.target_format));
        Ok(Box::new(Desktop(Workbench::new(&cc.egui_ctx,url,token))))
    }))
}
