from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# 收集tqdm的所有子模块
hiddenimports = collect_submodules('tqdm')

# 添加特别容易丢失的模块
hiddenimports += [
    'tqdm.auto',
    'tqdm.std',
    'tqdm.utils',
    'tqdm._tqdm',
    'tqdm._tqdm_pandas',
    'tqdm._tqdm_notebook',
    'tqdm._tqdm_gui',
    'tqdm._tqdm_tk',
    'tqdm._tqdm_qt',
    'tqdm._tqdm_gtk',
    'tqdm._tqdm_widgets',
]

# 收集数据文件
datas = collect_data_files('tqdm') 