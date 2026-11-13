"""Run the same real capture/native-output harness as DA2 Small."""
import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'v1'))
from trial import installed, worker

if __name__ == '__main__':
    os.environ['SCREENTO3D_STEREO_RENDERER'] = 'cuda'
    os.environ['SCREENTO3D_GPU_CAPTURE'] = '1'
    with installed():
        from screento3d_app import live_sbs
        live_sbs.sbs_worker = worker
        from benchmark_live_modes import main
        main()
