use std::{collections::HashSet,sync::Arc,time::{Duration,Instant}};
use serde_json::{Value,json};
use crate::{client::{Client,Request},render::SceneCallback,scene::Scene};

fn id()->String {uuid::Uuid::new_v4().simple().to_string()}
fn text(v:&Value,k:&str)->String {v[k].as_str().unwrap_or("").to_owned()}

pub struct Workbench {
    pub scene:Arc<Scene>,pub revision:u64,
    client:Client,url:String,token:String,pair_code:String,devices:Vec<Value>,actions:Vec<Value>,
    selected_node:String,workspace:String,task:String,artifacts:Vec<Value>,field_path:String,
    session:String,sessions:Vec<Value>,messages:Vec<Value>,chat:String,logs:String,status:String,
    project_name:String,mode:String,axis:usize,index:usize,level:f64,timestep:usize,
    yaw:f32,pitch:f32,zoom:f32,last_poll:Instant,loaded:HashSet<String>,pending:HashSet<String>,
    templates:Value,last_action:Option<Value>,probe:[f64;3],connected:bool,
}

impl Workbench {
    pub fn new(ctx:&egui::Context,url:String,token:String)->Self {
        let mut fonts=egui::FontDefinitions::default();
        fonts.font_data.insert("noto-sc".into(),egui::FontData::from_static(include_bytes!("../assets/NotoSansSC.ttf")).into());
        fonts.families.entry(egui::FontFamily::Proportional).or_default().push("noto-sc".into());
        fonts.families.entry(egui::FontFamily::Monospace).or_default().push("noto-sc".into());
        ctx.set_fonts(fonts);
        let mut visuals=egui::Visuals::dark();
        visuals.panel_fill=egui::Color32::from_rgb(31,31,40);
        visuals.selection.bg_fill=egui::Color32::from_rgb(51,85,105);
        ctx.set_visuals(visuals);
        Self {scene:Arc::new(Scene::demo()),revision:0,client:Client::new(ctx.clone()),url,token,pair_code:String::new(),
            devices:vec![],actions:vec![],selected_node:String::new(),workspace:String::new(),task:String::new(),artifacts:vec![],field_path:String::new(),
            session:id(),sessions:vec![],messages:vec![],chat:String::new(),logs:String::new(),status:"尚未连接控制服务".into(),project_name:"科学项目".into(),
            mode:"slice".into(),axis:2,index:0,level:0.,timestep:0,yaw:0.8,pitch:0.6,zoom:1.6,last_poll:Instant::now()-Duration::from_secs(10),
            loaded:HashSet::new(),pending:HashSet::new(),templates:json!({}),last_action:None,probe:[0.;3],connected:false}
    }

    fn request(&self,tag:&str,method:&str,path:&str,body:Option<Value>) {
        let _=self.client.send.send(Request {tag:tag.into(),method:method.into(),path:path.into(),body,url:self.url.clone(),token:self.token.clone()});
    }
    fn refresh(&mut self) {
        if self.pending.insert("poll".into()) { self.request("devices","GET","devices",None);self.request("actions","GET","actions",None); }
    }
    fn action(&mut self,kind:&str,payload:Value) {
        if self.selected_node.is_empty() {self.status="请先选择执行节点".into();return;}
        let body=json!({"id":id(),"node_id":self.selected_node,"kind":kind,"payload":payload});
        self.last_action=Some(body.clone());
        self.request("submitted","POST","actions",Some(body));
    }
    fn view(&mut self) {
        if self.field_path.is_empty() {return;}
        let mut options=json!({"mode":self.mode,"axis":self.axis,"timestep":self.timestep});
        if self.mode=="slice" {options["index"]=json!(self.index);}
        if self.mode=="iso" {options["level"]=json!(self.level);}
        if self.mode=="vectors" {options["component"]=json!("magnitude");}
        self.action("view.build",json!({"task_id":self.task,"path":self.field_path,"options":options}));
    }
    fn receive(&mut self) {
        while let Ok(reply)=self.client.receive.try_recv() {
            if reply.tag=="devices" {self.pending.remove("poll");}
            match reply.result {
                Err(e)=>{self.status=e;},
                Ok(data)=> match reply.tag.as_str() {
                    "pair"=>{self.token=text(&data,"token");self.pair_code.clear();self.connected=true;self.refresh();self.request("templates","GET","templates",None);self.request("sessions","GET","sessions",None);},
                    "devices"=>{self.devices=data.as_array().cloned().unwrap_or_default();self.status="控制服务已连接".into();},
                    "templates"=>{self.templates=data;},
                    "sessions"=>{self.sessions=data.as_array().cloned().unwrap_or_default();},
                    "chat"=>{self.messages=data["messages"].as_array().cloned().unwrap_or_default();},
                    "actions"=>{
                        self.actions=data.as_array().cloned().unwrap_or_default();
                        for a in &self.actions {
                            let a_id=text(a,"id");
                            if text(a,"state")=="succeeded" && !self.loaded.contains(&a_id) && self.pending.insert(a_id.clone()) {
                                self.request("result","GET",&format!("actions/{a_id}"),None);
                            }
                        }
                    },
                    "result"=>{
                        let a_id=text(&data,"id");self.pending.remove(&a_id);self.loaded.insert(a_id);
                        let result=&data["result"];
                        // A view belongs to its node/task; never replace a newer selection with another task's view.
                        let same_task=text(&data["request"]["payload"],"task_id")==self.task;
                        match data["request"]["kind"].as_str().unwrap_or("") {
                            "workspace.create"=>{self.workspace=text(result,"id");},
                            "task.submit"=>{self.task=text(result,"id");},
                            "task.artifacts" if same_task=>{self.artifacts=result.as_array().cloned().unwrap_or_default();},
                            "task.logs" if same_task=>{self.logs=result.to_string();},
                            "view.build" if same_task=> match serde_json::from_value::<Scene>(result.clone()) {
                                Ok(scene)=>match scene.validate() {Ok(())=>{self.level=(scene.manifest.value_range[0]+scene.manifest.value_range[1])/2.;self.scene=Arc::new(scene);self.revision+=1;},Err(e)=>self.status=e},
                                Err(e)=>self.status=e.to_string()},
                            "view.probe" if same_task=>{self.logs=serde_json::to_string_pretty(result).unwrap_or_default();},
                            _=>{}
                        }
                    },
                    _=>{self.refresh();}
                }
            }
        }
    }

    pub fn ui(&mut self,root:&mut egui::Ui) {
        self.receive();
        if self.connected && self.last_poll.elapsed()>Duration::from_secs(3) {self.refresh();self.last_poll=Instant::now();}
        if self.connected {root.ctx().request_repaint_after(Duration::from_secs(3));}
        egui::Panel::top("connection").show(root,|ui| {
            ui.horizontal(|ui| {ui.strong("STK / 科学工作台");ui.separator();
                ui.add(egui::TextEdit::singleline(&mut self.url).desired_width(230.).hint_text("控制服务地址"));
                ui.add(egui::TextEdit::singleline(&mut self.token).password(true).desired_width(100.).hint_text("设备凭据"));
                if ui.button("连接").clicked() {self.connected=true;self.refresh();self.request("templates","GET","templates",None);self.request("sessions","GET","sessions",None);}
                ui.add(egui::TextEdit::singleline(&mut self.pair_code).password(true).desired_width(100.).hint_text("配对码"));
                if ui.button("配对").clicked() {self.request("pair","POST","pairings/claim",Some(json!({"code":self.pair_code,"name":"STK 原生工作台"})));}
            });
            ui.label(&self.status);
        });
        egui::Panel::left("projects").resizable(true).default_size(235.).show(root,|ui| {
            ui.heading("项目与任务");
            egui::ScrollArea::vertical().id_salt("projects-scroll").show(ui,|ui| {
                for node in self.devices.clone().iter().filter(|n|n["role"]=="node") {
                    let n=text(node,"id");
                    let label=format!("{} {}",if node["online"]==true {"●"} else {"○"},text(node,"name"));
                    if ui.selectable_label(self.selected_node==n,label).clicked() {self.selected_node=n;self.workspace.clear();self.task.clear();self.artifacts.clear();}
                    if node["online"]!=true {ui.small(format!("最近连接：{}",node["last_seen"]));}
                    if self.selected_node==text(node,"id") {
                        if let Some(workspaces)=node["snapshot"]["workspaces"].as_array() {for w in workspaces {
                            if ui.selectable_label(self.workspace==text(w,"id"),text(w,"name")).clicked() {self.workspace=text(w,"id");}
                        }}
                        if let Some(tasks)=node["snapshot"]["tasks"].as_array() {for t in tasks {
                            if ui.selectable_label(self.task==text(t,"id"),format!("{} · {}",text(t,"name"),text(t,"state"))).clicked() {
                                self.task=text(t,"id");self.artifacts.clear();self.action("task.artifacts",json!({"task_id":self.task}));
                            }
                        }}
                    }
                }
                ui.separator();ui.text_edit_singleline(&mut self.project_name);
                if ui.button("新建项目").clicked() {self.action("workspace.create",json!({"name":self.project_name}));}
                if ui.add_enabled(!self.workspace.is_empty(),egui::Button::new("运行解析场示例")).clicked() {
                    self.action("task.submit",json!({"template":"demo-field","spec":{"workspace_id":self.workspace,"name":"解析场验证", "argv":["@python","-m","suan.control.demo_job"],"outputs":["scalar-0.vti","scalar-1.vti","vector.vti"]}}));
                }
                if !self.task.is_empty() {ui.horizontal(|ui| {
                    if ui.button("日志").clicked() {self.action("task.logs",json!({"task_id":self.task}));}
                    if ui.button("结果").clicked() {self.action("task.artifacts",json!({"task_id":self.task}));}
                    if ui.button("取消任务").clicked() {self.action("task.cancel",json!({"task_id":self.task}));}
                });}
                for a in self.actions.clone().iter().filter(|a|a["state"]=="review") {
                    ui.separator();ui.colored_label(egui::Color32::YELLOW,"等待执行复核");ui.label(text(a,"review_reason"));
                    ui.label(serde_json::to_string_pretty(&a["request"]["payload"]).unwrap_or_default());
                    ui.horizontal(|ui| {for (label,approved) in [("批准",true),("拒绝",false)] {if ui.button(label).clicked() {
                        self.request("review","POST",&format!("actions/{}/review",text(a,"id")),Some(json!({"approved":approved})));
                    }}});
                }
                if let Some(body)=self.last_action.clone() {if ui.button("重试上次操作（同一 ID）").clicked() {self.request("submitted","POST","actions",Some(body));}}
            });
        });
        egui::Panel::right("properties").resizable(true).default_size(260.).show(root,|ui| {
            ui.heading("视图与参数");ui.label(&self.scene.manifest.field);
            ui.label(format!("值域 {:.5} → {:.5} {}",self.scene.manifest.value_range[0],self.scene.manifest.value_range[1],self.scene.manifest.units));
            egui::ComboBox::from_label("结果文件").selected_text(&self.field_path).show_ui(ui,|ui| {for a in &self.artifacts {let path=text(a,"path");if path.ends_with(".vti")||path.ends_with(".vtk")||path.ends_with(".npy")||path.ends_with(".dat") {ui.selectable_value(&mut self.field_path,path.clone(),path);}}});
            ui.horizontal(|ui| {ui.selectable_value(&mut self.mode,"slice".into(),"切片");ui.selectable_value(&mut self.mode,"iso".into(),"等值面");ui.selectable_value(&mut self.mode,"vectors".into(),"向量");});
            ui.horizontal(|ui| {for (i,a) in ["X","Y","Z"].iter().enumerate(){ui.selectable_value(&mut self.axis,i,*a);}});
            ui.add(egui::DragValue::new(&mut self.index).prefix("切片索引 ").range(0..=100000));
            ui.add(egui::DragValue::new(&mut self.level).prefix("等值 ").speed(0.1));
            ui.add(egui::DragValue::new(&mut self.timestep).prefix("时间步标签 "));
            if ui.button("加载所选结果").clicked() {self.view();}
            ui.separator();ui.label("数值探针 · 原始数据");for v in &mut self.probe {ui.add(egui::DragValue::new(v).speed(0.1));}
            if ui.button("查询物理坐标").clicked() {self.action("view.probe",json!({"task_id":self.task,"path":self.field_path,"position":self.probe}));}
            ui.separator();ui.label("AI 对话");
            egui::ComboBox::from_id_salt("sessions").selected_text("恢复会话").show_ui(ui,|ui| {for s in &self.sessions {if ui.selectable_label(self.session==text(s,"id"),text(s,"name")).clicked() {self.session=text(s,"id");self.request("chat","GET",&format!("sessions/{}",self.session),None);}}});
            egui::ScrollArea::vertical().id_salt("chat-scroll").max_height(220.).stick_to_bottom(true).show(ui,|ui| {for m in &self.messages {ui.strong(if m["role"]=="user" {"你"}else{"STK"});ui.label(text(m,"content"));}});
            ui.add(egui::TextEdit::multiline(&mut self.chat).hint_text("描述计算任务…").desired_rows(3));
            if ui.button("发送").clicked()&&!self.chat.trim().is_empty() {self.request("chat","POST",&format!("sessions/{}/messages",self.session),Some(json!({"id":id(),"content":self.chat})));self.chat.clear();}
        });
        egui::Panel::bottom("logs").resizable(true).default_size(120.).show(root,|ui| {
            ui.strong("日志 / 探针结果");egui::ScrollArea::both().show(ui,|ui| {ui.monospace(&self.logs);});
        });
        egui::CentralPanel::default().show(root,|ui| {
            ui.horizontal(|ui| {ui.heading("三维视图");ui.label("拖动旋转 · 滚轮缩放 · 单击选取");if ui.button("复位").clicked() {self.yaw=0.8;self.pitch=0.6;self.zoom=1.6;}});
            let (rect,response)=ui.allocate_exact_size(ui.available_size().max(egui::vec2(1.,1.)),egui::Sense::click_and_drag());
            if response.dragged() {let delta=response.drag_motion();self.yaw-=delta.x*0.01;self.pitch=(self.pitch+delta.y*0.01).clamp(-1.5,1.5);}
            if response.hovered() {let scroll=ui.input(|i|i.smooth_scroll_delta.y);self.zoom=(self.zoom*(-scroll*0.002).exp()).clamp(0.2,20.);}
            let matrix=self.scene.matrix(self.yaw,self.pitch,self.zoom,rect.width()/rect.height());
            ui.painter().rect_filled(rect,0.,egui::Color32::from_rgb(22,25,33));
            ui.painter().add(egui_wgpu::Callback::new_paint_callback(rect,SceneCallback {scene:self.scene.clone(),matrix,revision:self.revision}));
            if response.clicked() {if let Some(p)=response.interact_pointer_pos() {
                let ndc=[(p.x-rect.left())/rect.width()*2.-1.,1.-(p.y-rect.top())/rect.height()*2.];
                if let Some(point)=self.scene.pick(matrix,ndc) {self.probe=point;self.status=format!("选取物理坐标：{point:.5?}");}
            }}
        });
    }
}
