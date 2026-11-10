---
title: Workbench guide
description: Open conversations, track tasks and inspect results in the desktop and Web clients.
---

In both STK clients, **Workbench** opens conversations, **Tasks** shows runs, and **Results** shows files and 3D output. Moving between these pages preserves the current draft, task selection and Viewer camera. Use the separate controls to send a message, submit a task or open a result.

## Desktop client

1. From **Workbench**, choose **Overview** to open a local project or select **Create example project**. The example contains parameters, synthetic field data and a completed analysis.
2. Open recent questions or agent sessions from the sidebar. In a narrow window, open **History**. Use **Overview** for project tables, files and analyses, or **Split view** to use multiple tools side by side.
3. In **Tasks**, choose a connection and a task. Click **Open in Viewer** on the selected task to open its published output. Expand **Source** to check the task and time step.

[Linux quickstart](/en/quickstart/) · [Build on macOS and Windows](https://github.com/sijintech/stk/blob/main/desktop/QUICKSTART.md)

## Web workbench

1. Open your STK control service and connect using a client pairing code issued by its administrator. The Web workbench opens on **工作台** (Workbench). Create a conversation or open history from the sidebar. In a narrow window, use **历史** (History).
2. Under **任务 → 运行环境** (Tasks → Run environment), choose a node and a run workspace, then select a task from the queue. After the first workspace selection, the environment folds into a summary showing the current node and workspace. Open it again to change either selection.
3. Open **结果** (Results) from the selected task. In **结果文件** (Result files), choose a file and click **加载视图** (Load view). In **图谱** (Graph), choose a preset and click **计算图谱** (Evaluate graph). Expand **来源** (Source) to check the task, file or step shown.
4. For a successful MuPRO task that published `case/run.h5` and its SHA-256, open **图谱 → MuPRO HDF5** and click **列出 HDF5 帧** (List HDF5 frames). Choose a field and a step. Component indices start at 0. Click **打开所选 HDF5 帧** (Open selected HDF5 frame) to load the selection.

The Web run workspace belongs to the paired execution node. The local desktop project holds its own tables, files and analysis records. Check the connection and object shown in **Source** when moving between clients.

[Pair a Web client and a node](https://github.com/sijintech/stk/blob/main/docs/hub.md) · [MuPRO workflow and HDF5 results](https://github.com/sijintech/stk/blob/main/docs/simulation-muferro.md)

## Legacy interface

The sidebar also provides access to the older PyQt documentation. [Legacy PyQt user guide](/en/user_guide/pyqt/)
