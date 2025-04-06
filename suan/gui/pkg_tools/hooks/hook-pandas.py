# -*- coding: utf-8 -*-
"""
Pandas模块的PyInstaller钩子 (自动生成)
处理pandas的隐藏依赖
"""

from PyInstaller.utils.hooks import collect_submodules

# 自动生成的依赖列表
hiddenimports = ['pandas._libs.tslibs.timedeltas', 'pandas._libs.tslibs.nattype', 'pandas._libs.tslibs.np_datetime', 'pandas._libs.tslibs.base', 'pandas._libs.tslibs.conversion', 'pandas._libs.tslibs.fields', 'pandas._libs.tslibs.offsets', 'pandas._libs.tslibs.parsing', 'pandas._libs.tslibs.period', 'pandas._libs.tslibs.strptime', 'pandas._libs.tslibs.vectorized']

# 收集额外的子模块
additional_modules = collect_submodules('pandas')
for module in additional_modules:
    if module not in hiddenimports:
        hiddenimports.append(module)

print(f"Pandas钩子: 收集了 {len(hiddenimports)} 个子模块")
