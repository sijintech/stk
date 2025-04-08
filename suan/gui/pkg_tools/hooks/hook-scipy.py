from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# 收集scipy的所有子模块
hiddenimports = collect_submodules('scipy')

# 添加特别容易丢失的模块
hiddenimports += [
    'scipy.special._cdflib',
    'scipy.special._ufuncs',
    'scipy.special._ellip_harm_2',
    'scipy.special._comb',
    'scipy.integrate',
    'scipy.integrate.quadrature',
    'scipy.integrate.odepack',
    'scipy.integrate._odepack',
    'scipy.integrate.quadpack',
    'scipy.integrate._quadpack',
    'scipy.integrate._ode',
    'scipy.integrate.vode',
    'scipy.integrate._dop',
    'scipy.integrate.lsoda',
    'scipy._lib.messagestream',
]

# 收集数据文件
datas = collect_data_files('scipy') 