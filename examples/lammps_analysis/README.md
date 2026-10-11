# E1c：可复现曲线与真实 LAMMPS 路径

`data/` 是公开的合成曲线，只验证分析公式：两段密度线交点 **340 K**，带预载的应力曲线模量 **2.5 GPa**，
长时 MSD 对应三维扩散系数 **1×10⁻⁴ cm²/s**。它们不是 PET 或其他材料的测量/模拟数据。

从仓库根目录、装有 STK science/test 依赖的 Python 环境执行，输出写到新目录：

```bash
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= suan graph run lammps-tg \
  --bind data=examples/lammps_analysis/data --out /tmp/stk-tg-example
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= suan graph run lammps-modulus \
  --bind data=examples/lammps_analysis/data --out /tmp/stk-modulus-example
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= suan graph run lammps-diffusion \
  --bind data=examples/lammps_analysis/data --param time_min=1000 --param time_max=10000 \
  --out /tmp/stk-diffusion-example
```

查看 `summary`、`fit`、`diagnostics`、曲线和警告；扩散不填窗口应失败。
通用运行、物理含义与限制见[分析指南](../../docs/lammps-analysis.md)。

## 真实程序验收（手动，不进入默认 CI）

`acceptance/test_real_templates.py` 生成公开的 **108 原子 FCC 氩**夹具，直接使用三套已安装模板；
通过真实 Runtime、项目按行工作流、冻结日志/结果、隔离分析工作进程和归档读回，检查完整路径。
Tg 分支验证一个温度的密度点；真实 Tg 需要多温度汇总与研究协议，本验收不计算氩的 Tg。
模量/扩散分支检查有限结果及绘图，不把短轨迹拟合值当作收敛性质。
程序缺失时失败，不跳过；项目与输出保留在 pytest 临时目录。

```bash
PYTHONPATH=.:tests env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= \
  STK_LAMMPS=/absolute/path/to/lmp STK_E1C_REPORT_DIR=/tmp/new-e1c-report \
  /absolute/science/python -m pytest examples/lammps_analysis/acceptance \
  -p conftest --rootdir=examples/lammps_analysis/acceptance -s -q -p no:cacheprovider
```

`STK_E1C_REPORT_DIR` 可省略；设置后保存每项的参数、实际输出与冻结产物 SHA-256。
报告目录中的同名报告已存在时拒绝覆盖。此夹具不依赖 foyer/GMSO，也不使用待决定的 PET 电荷。

2026-10-11 用 LAMMPS 22 Jul 2025 Update 6 MPICH 版验收 **3 passed**，报告为
[密度点](validation/2026-10-11-tg.json)、[拉伸](validation/2026-10-11-modulus.json)、[MSD](validation/2026-10-11-diffusion.json)。
设定 20 K 的密度点均温 20.775 K、密度 1.74923 g/cm³；短时拉伸拟合 2.43161 GPa，
300 K MSD 在 100–1000 fs 的路径验收拟合 1.79843e-4 cm²/s。后两项仅是该短轨迹的实际软件输出，
**不是氩或 PET 的收敛性质**。报告保留完整运行参数、分析窗口、输入和日志摘要。
