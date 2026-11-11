---
title: Workbench guide
description: Open conversations, track tasks and inspect results in the desktop and Web clients.
---

In both STK clients, **Workbench** opens conversations, **Tasks** shows runs, and **Results** shows files and 3D output. Moving between these pages preserves the current draft, task selection and Viewer camera. Use the separate controls to send a message, submit a task or open a result.

In a wide window, the left sidebar holds all three pages and history. In a narrow window, open **History** from the top navigation to write or return to earlier work.

## Desktop client

1. From **Workbench**, choose **Overview** to open a local project or select **Create example project**. The example contains parameters, synthetic field data and a completed analysis.
2. Choose **Write question** to return directly to the current project draft, or open recent questions and agent sessions from the sidebar. Choose **Saved questions** to browse the full list. In a narrow window, open **History** first. Use **Overview** for project tables, files and analyses, or **Split view** to use multiple tools side by side.
3. Open **Tasks**. With no valid workspace selected, **Run environment** opens by default. Choose a **Connection**. For a control service connection, also choose a **Node**. Under **Workspace**, click **New…**, enter a **Name** and click **OK**. When the current Tasks page selects the new workspace, the **New task** form opens by default. Fill it in and click **Submit**.
4. Selecting an existing workspace keeps the **New task** form and its draft as they were. A form you collapsed stays collapsed when you create a workspace. The run workspace holds task inputs and outputs on the chosen connection. Open **Overview** to manage the local project.
5. In **Tasks**, choose a task. Click **Open in Viewer** on the selected task to open its published output. Expand **Source** to check the task and time step.
6. After opening a collected MuPRO HDF5 frame, open **Source** in the Viewer. Enter the zero-based X, Y and Z grid indices and click **Read voxel**. The result identifies the displayed field, step, component and original value.

[Linux quickstart](/en/quickstart/) · [Build on macOS and Windows](https://github.com/sijintech/stk/blob/main/desktop/QUICKSTART.md)

## Web workbench

1. Open your STK control service and connect using a client pairing code issued by its administrator. The Web workbench opens on **工作台** (Workbench). Create a conversation or open history from the sidebar. In a narrow window, use **历史** (History).
2. Open **任务** (Tasks). While no workspace is selected, **运行环境** (Run environment) is expanded. Choose a node under **执行节点** (Execution node). **项目** (Project) lists the run workspaces on that node. Choose one, or type a name in the box beside **新建** (Create), which starts as 科学项目, and click **新建**. After the first workspace selection, the environment folds into a summary showing the current node and workspace. Open it again to change either selection. You can then select a task from the queue.
3. When a workspace you created is selected on the current page, **新建任务** (New task) opens by default. Its title may show the first eight characters of the workspace ID until the node reports the name. Click **运行解析场示例** (Run analytic field example), or edit the TaskSpec JSON below 自定义任务 (Custom task) and click **提交复核** (Submit for review). Changing the selection keeps the form and draft as they were. A form you collapsed stays collapsed.
4. A custom task targets the workspace named in **新建任务** (New task). You can omit `workspace_id` from the JSON. If the draft names a different workspace, the form keeps the draft and asks you to check the destination. Edit or remove the field, or choose the intended workspace under **运行环境** (Run environment).
5. Open **结果** (Results) from the selected task. For a successful task with one viewable file, **结果文件** (Result files) preselects it if the picker is still in its initial state. Confirm the file and click **加载视图** (Load view). In **图谱** (Graph), choose a preset and click **计算图谱** (Evaluate graph). Expand **来源** (Source) to check the task, file or step shown.
6. For a successful MuPRO task that published `case/run.h5` and its SHA-256, open **图谱 → MuPRO HDF5** and click **列出 HDF5 帧** (List HDF5 frames). Choose a field and a step. Component indices start at 0. Click **打开所选 HDF5 帧** (Open selected HDF5 frame). Then enter the zero-based X, Y and Z grid indices and click **读取体素** (Read voxel) to query the frame on screen.

The Web run workspace belongs to the paired execution node. The local desktop project holds its own tables, files and analysis records. Check the connection and object shown in **Source** when moving between clients.

[Pair a Web client and a node](https://github.com/sijintech/stk/blob/main/docs/hub.md) · [MuPRO workflow and HDF5 results](https://github.com/sijintech/stk/blob/main/docs/simulation-muferro.md)

## Legacy interface

The sidebar also provides access to the older PyQt documentation. [Legacy PyQt user guide](/en/user_guide/pyqt/)
