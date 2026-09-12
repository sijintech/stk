"""Bridge the installed entry point to the existing desktop's local imports."""

from pathlib import Path
import runpy
import sys


def main():
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))
    runpy.run_path(str(root / 'main.py'), run_name='__main__')
