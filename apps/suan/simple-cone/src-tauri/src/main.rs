#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

use async_std::task;
use std::time::Duration;
use tauri::api::process::{Command, CommandEvent};
use tauri::Manager;

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            println!("app start.......");

            let splashscreen_window = app.get_window("splashscreen").unwrap();
            let main_window = app.get_window("main").unwrap();
            let (mut rx, _) = Command::new_sidecar("trame")
                .expect("failed to create sidecar")
                .args(["--server", "--port", "8080", "--timeout", "10000"])
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
            println!("trame server1.......");
            });
            println!("trame server.......");
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running application");
}
