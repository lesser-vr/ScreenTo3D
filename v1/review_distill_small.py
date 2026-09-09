"""Make fixed native-pixel eye crops from completed public comparison stills."""
import argparse
import json

import cv2
import numpy as np

from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    report = json.loads((args.directory/'report.json').read_text())
    if report['status'] != 'measured' or report['combined'] != [7680, 2160]:
        raise ValueError('Completed full-SBS comparison required')
    destination = args.directory/'eye-crops'
    destination.mkdir(exist_ok=False)
    regions = {'FloorballGame': (800, 500, 1100, 1100),
               'OfficeWalk': (1200, 1050, 1100, 1100),
               'ParkingGarage': (1400, 200, 1100, 1100)}
    for source, (x, y, width, height) in regions.items():
        rows = []
        for model in ('da2', 'distill'):
            sbs = cv2.imread(str(args.directory/f'{source}-0-{model}-sbs.png'))
            if sbs is None or sbs.shape != (2160, 7680, 3):
                raise ValueError('Invalid paired image')
            tiles = []
            for eye, offset in (('left', 0), ('right', 3840)):
                crop = sbs[y:y+height, x+offset:x+offset+width].copy()
                cv2.rectangle(crop, (0, 0), (400, 50), (0, 0, 0), -1)
                cv2.putText(crop, f'{model} {eye}', (15, 35), cv2.FONT_HERSHEY_SIMPLEX,
                            1, (255, 255, 255), 2)
                tiles.append(crop)
            rows.append(np.hstack(tiles))
        if not cv2.imwrite(str(destination/f'{source}.png'), np.vstack(rows)):
            raise RuntimeError('Crop write failed')
    (destination/'regions.json').write_text(json.dumps(regions, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
