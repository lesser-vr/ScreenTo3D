"""Labeled diagnostic crops from existing synchronized source/SBS videos."""
import argparse
from pathlib import Path
import cv2
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    parser.add_argument('--roi', nargs=4, type=int, default=[400, 160, 800, 500])
    args = parser.parse_args()
    x0, y0, x1, y1 = args.roi
    rows = []
    for name in ('input', 'small', 'base', 'vda'):
        capture = cv2.VideoCapture(str(args.folder/f'{name}.mp4'))
        try:
            tiles = []
            for index in (0, 30, 60, 90, 119):
                capture.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, im = capture.read()
                if not ok: raise ValueError('Missing timeline frame')
                w = im.shape[1] if name == 'input' else im.shape[1]//2
                if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= im.shape[0]):
                    raise ValueError('Invalid review ROI')
                crop = im[y0:y1, x0:x1]  # source or left eye, never mixed eyes
                crop = cv2.resize(crop, (320, round((y1-y0)*320/(x1-x0))))
                header = np.full((30, 320, 3), 240, np.uint8)
                cv2.putText(header, f'{name} left f{index}', (5, 21), cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 0, 0), 1)
                tiles.append(np.concatenate([header, crop], axis=0))
            rows.append(np.concatenate(tiles, axis=1))
        finally: capture.release()
    target = args.folder/'left-boundary-timeline.jpg'
    if not cv2.imwrite(str(target), np.concatenate(rows, axis=0)): raise RuntimeError('Write failed')
    print(target)


if __name__ == '__main__': main()
