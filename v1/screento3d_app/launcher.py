"""Console-free entry point with a launcher-owned UTF-8 error log."""
import faulthandler
import os
import sys
import traceback


from .environment import required as app_env_required

def main():
    with open(app_env_required('SCREENTO3D_LAUNCH_LOG'), "a", encoding="utf-8", buffering=1) as log:
        sys.stdout = sys.stderr = log
        faulthandler.enable(log)
        try:
            from .user_data import prepare_environment
            prepare_environment()
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
