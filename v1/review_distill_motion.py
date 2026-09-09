"""Decode native-pixel eye crops at six timestamps from measured public videos."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    report = json.loads((args.directory/'report.json').read_text())
    if report['status'] != 'measured' or report['combined'] != [7680, 2160]:
        raise ValueError('Measured full-SBS recording required')
    output = args.directory/'motion-review'
    output.mkdir(exist_ok=False)
    regions = {'FloorballGame': (1150, 850), 'OfficeWalk': (1500, 900), 'ParkingGarage': (1450, 750)}
    indices = (0, 60, 120, 180, 240, 359)
    for source, (x, y) in regions.items():
        rows = []
        for model in ('da2', 'distill'):
            cap = cv2.VideoCapture(str(args.directory/f'{source}-{model}.mp4'))
            tiles = [[], []]
            try:
                for index in range(360):
                    ok, frame = cap.read()
                    if not ok or frame.shape != (2160, 7680, 3):
                        raise ValueError('Incomplete or invalid recording')
                    if index in indices:
                        for eye, offset in enumerate((0, 3840)):
                            tile = frame[y:y+384, x+offset:x+offset+384].copy()
                            cv2.rectangle(tile, (0, 0), (383, 28), (0, 0, 0), -1)
                            cv2.putText(tile, f'{model} eye{eye} f{index}', (5, 20),
                                        cv2.FONT_HERSHEY_SIMPLEX, .5, (255, 255, 255), 1)
                            tiles[eye].append(tile)
            finally:
                cap.release()
            rows.extend(np.hstack(eye) for eye in tiles)
        if not cv2.imwrite(str(output/f'{source}.png'), np.vstack(rows)):
            raise RuntimeError('Review sheet write failed')
    (output/'scope.json').write_text(json.dumps(dict(regions=regions, crop=[384, 384],
        frames=indices, scope='Native-pixel sampled eye crops, not playback or fused headset review.'), indent=2))


if __name__ == '__main__':
    main()
