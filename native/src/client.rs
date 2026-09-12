use serde_json::Value;
use std::{sync::mpsc, time::Duration};

pub struct Request {pub tag:String,pub method:String,pub path:String,pub body:Option<Value>,pub url:String,pub token:String}
pub struct Reply {pub tag:String,pub result:Result<Value,String>}
pub struct Client {pub send:mpsc::Sender<Request>,pub receive:mpsc::Receiver<Reply>}

pub fn validate_origin(url:&str)->Result<(),String> {
    let u=reqwest::Url::parse(url).map_err(|e|e.to_string())?;
    if !u.username().is_empty() || u.password().is_some() || u.query().is_some() || u.fragment().is_some()
        || !matches!(u.path(),""|"/") || (u.scheme()!="https" && !(u.scheme()=="http" && matches!(u.host_str(),Some("127.0.0.1"|"localhost"|"[::1]")))) {
        return Err("远程控制服务必须使用 HTTPS；本机可使用回环 HTTP。".into());
    }
    Ok(())
}

impl Client {
    pub fn new(ctx:egui::Context)->Self {
        let (send,requests)=mpsc::channel::<Request>();
        let (replies,receive)=mpsc::channel();
        std::thread::spawn(move|| {
            let http=reqwest::blocking::Client::builder().timeout(Duration::from_secs(90))
                .redirect(reqwest::redirect::Policy::none()).build().expect("HTTP client");
            for r in requests {
                let result=(|| {
                    validate_origin(&r.url)?;
                    let method=reqwest::Method::from_bytes(r.method.as_bytes()).map_err(|e|e.to_string())?;
                    let mut q=http.request(method,format!("{}/api/v1/{}",r.url.trim_end_matches('/'),r.path)).bearer_auth(&r.token);
                    if let Some(body)=r.body {q=q.json(&body);}
                    let response=q.send().map_err(|_|"连接失败；可重试同一操作。".to_string())?;
                    let status=response.status();
                    let data:Value=response.json().map_err(|_|"服务返回无效 JSON".to_string())?;
                    if !status.is_success() {return Err(format!("{}: {}",status,data.get("detail").unwrap_or(&data)));}
                    Ok(data)
                })();
                if replies.send(Reply {tag:r.tag,result}).is_err() {break;}
                ctx.request_repaint();
            }
        });
        Self {send,receive}
    }
}
