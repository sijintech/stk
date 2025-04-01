"""
Hook for rapidfuzz package to avoid errors related to __pyinstaller attribute
"""

# Define empty lists to prevent PyInstaller from looking for rapidfuzz.__pyinstaller
hiddenimports = []
datas = []
binaries = []

# This hook prevents the error:
# "Failed to process hook entry point 'EntryPoint(name='hook-dirs', value='rapidfuzz.__pyinstaller:get_hook_dirs'" 