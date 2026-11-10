"""Console-free entry point with a launcher-owned UTF-8 error log."""
import faulthandler
import os
import sys
import traceback


def main():
    with open(os.environ["DEPTHSBS_LAUNCH_LOG"], "a", encoding="utf-8", buffering=1) as log:
        sys.stdout = sys.stderr = log
        faulthandler.enable(log)
        try:
            from .desktop import main as desktop_main
            return desktop_main()
        except Exception:
            traceback.print_exc()
            return 1
        finally:
            faulthandler.disable()
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__


if __name__ == "__main__":
    sys.exit(main())
