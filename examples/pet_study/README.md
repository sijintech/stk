# PET 全流程研究

在项目编辑器的“材料仿真”面板选择 LAMMPS 和已保存的 Runtime，展开“PET 全流程模拟”。默认 `{}` 是短时软件试跑；编辑 JSON 后依次点“准备新的研究”和“开始 / 继续”。创建、状态查看和重开项目不会启动模拟。运行器使用项目格式 13 的持久工作流运行、快照、模拟运行和分析运行。

一次明确启动会完成：PET 建模 → 高温逐渐压密并释放到 1 atm → 依次降温并继承前一温度状态 → 在对应保存温度状态上进行应力应变和 MSD 采样 → 三种分析与诊断归档。各段的 `state.data`、`trajectory.dump`、日志、输入状态 SHA256 和源快照会保存。纯 PET 的 `pet_chain_com` 是聚合物链质心自扩散；气体试跑请使用 `{"diffusion":{"group":"o2_com"}}`，采用版本化的 O₂ IFF2021 参数。

短链和短时结果只验证软件流程。Tg 分段交点、模量或扩散拟合不满足条件时，保留失败分析和诊断；不会用人工数据补出物性。O₂ 示踪扩散不等于溶解度、渗透率或已收敛的阻隔性能。`{"mode":"research","diffusion":{"group":"o2_com"}}` 提供较大的起始预算；仍需检查密度、平衡、链长、多个独立构型、线性窗口和统计不确定度。

在脚本控制台中也可调用：

```python
study = stk.lammps.create_pet_study(
    {"diffusion": {"group": "o2_com"}},
    connection="runtime:your-saved-runtime",
    expected_revision=stk.project.snapshot()["project"]["revision"],
)
stk.lammps.start_pet_study(
    study["study_id"], expected_revision=stk.project.snapshot()["project"]["revision"]
)
# 此后只查看持久日志，不会额外提交计算。
status = stk.lammps.get_pet_study(study["study_id"])
```

关闭项目会停止桌面跟踪，已接受的 Runtime 任务继续运行；重开后先检查状态，需要恢复时点“恢复中断的研究”，再明确“开始 / 继续”。已成功的阶段不重跑，正在运行的任务会接回；“取消研究”会取消当前子任务。默认跟踪等待预算为试跑 24 小时、research 31 天，可通过脚本的 `wait_seconds` 指定。预算到期会停止跟踪，不取消已接受任务。

模拟运行列表的“查看结构 / 轨迹”读取校验过的采集结果；也可在 Viewer 中打开结果 case 目录并选择 `lammps-molecule`。原子 ID、分子 ID、类型、电荷来自文件，键来自真实拓扑。步数选择使用轨迹实际记录的步数，显示折回盒子不会改变原始非折回坐标或扩散分析。

实际软件验收（Linux，独立 core Python 与分子模块）:

```sh
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= \
  STK_MOLECULAR_PYTHON=/path/to/molecular-modeling/bin/python \
  STK_PACKMOL=/path/to/packmol/bin/packmol STK_LAMMPS=/path/to/lammps/bin/lmp \
  PYTHONPATH=.:tests python -m pytest -p conftest -s \
  examples/pet_study/acceptance/test_study_real.py
```

默认验收使用 546 PET 原子及 2 个 O₂ 分子，60 ps 压密、逐温度 5 ps 采样、50 ps 示踪扩散，逐个检查冻结文件、真实轨迹首尾帧、求解日志与三份分析归档，然后移动并离线重开项目。可用 `STK_PET_ACCEPTANCE_RECIPE` 指定公开配置 JSON、`STK_PET_ACCEPTANCE_TIMEOUT` 设置明确等待预算。实际耗时取决于计算节点；它不作物性收敛声明。

这些手动脚本仅适用于专用、隔离的公开材料软件验收 Runtime，不能接共享生产 Runtime 或企业内部数据。`test_resume_real.py` 只恢复同一测试创建的项目和 loopback Runtime，旧服务须先停止；它从脱敏连接 DTO 获取地址，使用公开测试占位令牌，不读取已有配置或凭据。恢复清理仅取消本研究 canonical 子运行的冻结、已接受任务 ID，并只协调这些任务的停止；不遍历取消其他 Runtime 任务。若本地来源不可验证，仅保留此前已核验 ID 的清理范围并报告。验收末尾按当前项目句柄定位目录，整体移动后离线重开不会移动其他已打开的项目。
