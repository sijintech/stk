#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

use async_std::task;
use std::time::Duration;
use tauri::api::process::{Command, CommandEvent};
use tauri::Manager;
//windows下
#[cfg(target_os = "windows")]
fn main() {
    tauri::Builder::default()
    //设置应用程序的初始化过程，这里主要用于创建和配置窗口，以及处理与应用程序初始化相关的其他任务
        .setup(|app| {
            println!("app start.......");

            let splashscreen_window = app.get_window("splashscreen").unwrap();
            let main_window = app.get_window("main").unwrap();
            //创建一个 Command 实例，表示即将执行的命令。new_sidecar 是 Tauri 提供的用于创建支持 Sidecar 模式的子进程的方法。Sidecar 模式是一种与 Tauri 主进程分离的模式，用于执行某些独立的任务，比如运行一个本地服务器。
            let (mut rx, _) = Command::new_sidecar("trame")
                .expect("failed to create sidecar")
                //指定子进程的命令行参数。在这里，传递了一些参数，包括 --server 表示启动服务器，--port 指定服务器端口为 0（表示由操作系统分配一个可用端口），--timeout 设置服务器启动的超时时间为 10 秒。
                .args(["--server", "--port", "8080", "--timeout", "10000"])
                //启动子进程。这一步会将命令传递给操作系统执行，启动名为 "trame" 的子进程。
                .spawn()
                .expect("Failed to spawn server");
            tauri::async_runtime::spawn(async move {
                println!("get windows.......");

                // while let Some(event) = rx.recv().await {
                //     println!("rx.recv().......");
                //     if let CommandEvent::Stdout(line) = event.clone() {
                //         println!("line:");
                //         println!("{}", line);
                //         if line.contains("trame-server-port=") {
                //             let tokens: Vec<&str> = line.split("=").collect();
                //             println!("Connect to port {}", tokens[1]);
                //             let r = main_window.eval(&format!(
                //                 "window.location.replace('http://localhost:{}')",
                //                 tokens[1]
                //             ));
                //             if r.is_err() {
                //                 println!("main_window.eval fail");
                //             }
                //             task::sleep(Duration::from_secs(2)).await;
                //             splashscreen_window.close().unwrap();
                //             main_window.show().unwrap();
                //         }
                //     }
                //     if let CommandEvent::Error(a) = event {
                //         println!("a:");
                //         println!("{}", a)
                //     }
                // }
                
                // 使用 Tauri 的主窗口实例执行 JavaScript 代码，将窗口的地址重定向到 Trame 服务器的地址
                let r = main_window.eval(&format!(
                    "window.location.replace('http://localhost:{}')",
                    8080
                ));
                if r.is_err() {
                    println!("main_window.eval fail");
                }
                task::sleep(Duration::from_secs(2)).await;
                splashscreen_window.close().unwrap();
                main_window.show().unwrap();
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running application");
}
// linux下
#[cfg(target_os = "linux")]
fn main() {
    tauri::Builder::default()
        .setup(|app| {
            println!("app start.......");

            let splashscreen_window = app.get_window("splashscreen").unwrap();
            let main_window = app.get_window("main").unwrap();
            let (mut rx, _) = Command::new_sidecar("trame")
                .expect("failed to create sidecar")
                .args(["--server", "--port", "0", "--timeout", "10000"])
                .spawn()
                .expect("Failed to spawn server");
                // 使用 Tauri 提供的异步运行时（tauri::async_runtime）启动一个异步任务，该任务会不断等待来自 Tauri 服务器子进程的事件。当监听到 "tauri-server-port=" 的输出时，解析出端口号，然后关闭启动窗口，显示主窗口。
          // 在异步任务中使用循环不断等待从异步通道 rx 接收到的事件。异步通道的 recv 方法会阻塞等待直到有新的事件到达。
            tauri::async_runtime::spawn(async move {
                println!("get windows.......");
                
                while let Some(event) = rx.recv().await {
                    println!("rx.recv().......");
                    if let CommandEvent::Stdout(line) = event.clone() {
                        println!("line:");
                        println!("{}", line);
                        if line.contains("trame-server-port=") {
                            let tokens: Vec<&str> = line.split("=").collect();
                            println!("Connect to port {}", tokens[1]);
                            let r = main_window.eval(&format!(
                                "window.location.replace('http://localhost:{}')",
                                tokens[1]
                            ));
                            if r.is_err() {
                                println!("main_window.eval fail");
                            }
                            task::sleep(Duration::from_secs(2)).await;
                            splashscreen_window.close().unwrap();
                            main_window.show().unwrap();
                        }
                    }
                    if let CommandEvent::Error(a) = event {
                        println!("a:");
                        println!("{}", a)
                    }
                }

                //windows下
                // let r = main_window.eval(&format!(
                //     "window.location.replace('http://localhost:{}')",
                //     49151
                // ));
                // if r.is_err() {
                //     println!("main_window.eval fail");
                // }
                // task::sleep(Duration::from_secs(5)).await;
                // splashscreen_window.close().unwrap();
                // main_window.show().unwrap();
            println!("trame server1.......");
            });
            println!("trame server.......");
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running application");
}
