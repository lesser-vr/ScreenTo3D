"""Record official-source provenance and independently check all 600 frame IDs."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'out/public-hfr'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    records=[]
    for name in ('Jockey','Beauty'):
        raw=OUT/f'{name}.hevc'; video=OUT/f'{name}-120.mp4'
        probe=json.loads(subprocess.check_output([shutil.which('ffprobe'),'-v','error','-select_streams','v:0',
            '-show_entries','stream=codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames:format=duration','-of','json',str(video)]))
        stream=probe['streams'][0]
        assert (stream['width'],stream['height'],stream['avg_frame_rate'],stream['nb_frames'])==(3840,2160,'120/1','600')
        digest_file=OUT/f'{name}-frames.md5'
        command=[shutil.which('ffmpeg'),'-hide_banner','-loglevel','error','-hwaccel','cuda',
                 '-i',str(video),'-vf','scale=64:36','-pix_fmt','gray','-fps_mode','passthrough',
                 '-f','framemd5','-y',str(digest_file)]
        subprocess.run(command,check=True)
        lines=[line for line in digest_file.read_text().splitlines() if line and not line.startswith('#')]
        hashes=[line.rsplit(',',1)[1].strip() for line in lines]
        assert len(hashes)==600 and len(set(hashes))==600
        records.append(dict(name=name,source_url=f'https://ultravideo.fi/video/{name}_3840x2160_120fps_420_8bit_HEVC_RAW.hevc',
            raw_sha256=sha(raw),raw_bytes=raw.stat().st_size,file_sha256=sha(video),file_bytes=video.stat().st_size,
            probe=probe,decoded_frames=len(hashes),unique_thumbnail_frames=len(set(hashes)),
            transform='Assign official 120fps timestamps to raw HEVC; NVDEC -> h264_nvenc p3 cq18; no interpolation, no frame duplication, no resize',
            timestamp_note='Raw elementary HEVC lacks usable container timing; ffprobe default 25fps is not the source shooting rate. Official dataset identifies 120fps/600 frames/5 seconds.'))
    report=dict(completed=True,source_page='https://ultravideo.fi/dataset.html',
        attribution='Ultra Video Group, Tampere University. A. Mercat, M. Viitanen, J. Vanne, UVG dataset: 50/120fps 4K sequences for video codec analysis and development, ACM MMSys 2020.',
        license='CC BY-NC 3.0, https://creativecommons.org/licenses/by-nc/3.0/',
        scope='Local noncommercial comparison; media not included in application release',records=records)
    (OUT/'manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
if __name__=='__main__':main()
