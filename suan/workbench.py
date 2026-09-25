"""Optional, deferred Synorder host launcher.

Not a console script of the base package; Synorder users run `python -m suan.workbench`
(equivalent to `synorder-native --workbench stk.workbench`).
"""
import sys


def main(argv=None):
    try:
        from synorder_native.launcher import main as launch
    except ImportError:
        raise SystemExit("Install the Synorder native host first, and enable synorder-stk on its Hub. See plugins/synorder/README.md.") from None
    return launch(["--workbench", "stk.workbench", *(sys.argv[1:] if argv is None else argv)])


if __name__ == "__main__":
    raise SystemExit(main())
