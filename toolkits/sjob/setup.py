# setup.py
from setuptools import setup

setup(
    name="sjob",
    version="0.1",
    py_modules=["sjob"],  # 模块的名称
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
            'sjob = cli:sjob',
        ],
    },
)
