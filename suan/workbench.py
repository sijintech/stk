"""STK customization is a Synorder plugin; this launcher contains no GUI code."""
import sys


def main(argv=None):
    try:
        from synorder_native.launcher import main as launch
    except ImportError:
        raise SystemExit("Install the Synorder native host first, and enable synorder-stk on its Hub. See plugins/synorder/README.md.") from None
    return launch(["--workbench", "stk.workbench", *(sys.argv[1:] if argv is None else argv)])


if __name__ == "__main__":
    raise SystemExit(main())
