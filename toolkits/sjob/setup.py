# setup.py
from setuptools import setup

setup(
    name="htpstudio",
    version="0.1",
    py_modules=["htpstudio"],  # 模块的名称
    install_requires=[
        # "subprocess",
        # "os",
        # "shutil",
        # "datetime",
        # "sys",
        # "re",
        # "argparse",
    ],
    entry_points={
        'console_scripts': [
            'htpstudio = htpstudio:runCommand',
        ],
    },
)
