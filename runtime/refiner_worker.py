"""Product Refiner worker: model and all media subprocesses share the guardian."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

from dreamx.refiner_recipe import final_command, inference_command, segment_counts, split_command
from dreamx.video_contract import RECIPE, padded_frames, output_rate, rate


class Worker:
    def __init__(self, spec, control=Path('/control'), job=Path('/job')):
        self.spec, self.control, self.job = spec, control, job
        self.child = None

    def healthy(self):
        guard = json.loads((self.control / 'guard-status.json').read_text())
        runner = json.loads((self.control / 'runner-heartbeat.json').read_text())
        active = json.loads((self.control / 'active.json').read_text())
        now = time.monotonic()
        return (active.get('job_id') == self.spec['job_id'] and active.get('container_id')
                and guard.get('container_id') == active['container_id']
                and not guard.get('reason') and 0 <= now - guard['at'] <= 2
                and 0 <= now - runner['at'] <= 2)

    def stop(self, *unused):
        if self.child is not None and self.child.poll() is None:
            os.killpg(self.child.pid, signal.SIGTERM)
            try:
                self.child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(self.child.pid, signal.SIGKILL)
                self.child.wait()
        raise SystemExit(143)

    def run(self, args, cwd=None, capture=False):
        if not self.healthy():
            self.stop()
        with tempfile.TemporaryFile(dir=self.job) as output:
            self.child = subprocess.Popen(args, cwd=cwd, start_new_session=True,
                                          stdout=output if capture else None)
            while self.child.poll() is None:
                try:
                    healthy = self.healthy()
                except Exception:
                    healthy = False
                if not healthy:
                    self.stop()
                time.sleep(.1)
            if self.child.returncode:
                raise RuntimeError('SUBPROCESS_FAILED')
            if capture:
                output.seek(0)
                data = output.read(1024 * 1024 + 1)
                if len(data) > 1024 * 1024:
                    raise ValueError('Oversized media evidence')
                return data

    def probe(self, path):
        return json.loads(self.run(['ffprobe', '-v', 'error', '-count_frames', '-show_streams',
                                    '-show_format', '-of', 'json', str(path)], capture=True))

    def audio_hash(self, path):
        return self.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-map', '0:a:0',
                         '-c:a', 'copy', '-f', 'hash', '-hash', 'sha256', '-'], capture=True).decode().strip()

    def main(self):
        spec = self.spec
        if spec.get('kind') != 'refine' or spec.get('recipe') != RECIPE or spec.get('seed') != 42:
            raise ValueError('Unsupported recipe')
        fps = output_rate(spec.get('output_fps', 24))
        frames = spec['frames']
        processing = padded_frames(frames)
        deadline = time.monotonic() + 30
        while True:
            try:
                go = json.loads((self.control / 'go.json').read_text())
                if go.get('job_id') == spec['job_id'] and self.healthy():
                    break
            except (OSError, ValueError, KeyError):
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError('GUARD_START_TIMEOUT')
            time.sleep(.1)
        source = Path('/input.mp4')
        original = digest(source)
        if original != spec['normalized_sha256']:
            raise ValueError('Input checksum mismatch')
        print('REFINER_PHASE preparing', flush=True)
        counts = segment_counts(frames, fps)
        segmented = len(counts) > 1
        if segmented:
            (self.job / 'chunks').mkdir()
            self.run(split_command(frames, fps))
            if len(list((self.job / 'chunks').glob('*.mp4'))) != len(counts):
                raise ValueError('Segment split count mismatch')
            processing = sum(padded_frames(n) for n in counts)
        self.run(inference_command(frames, segmented), cwd='/opt/dreamx/video_refiner')
        print('REFINER_PHASE muxing', flush=True)
        outputs = sorted((self.job / 'refined').glob('*.mp4'))
        if len(outputs) != len(counts) or any(p.is_symlink() for p in outputs):
            raise ValueError('Refined segment count mismatch')
        for index, (part, count) in enumerate(zip(outputs, counts)):
            if segmented and not part.name.startswith(f'{index:06d}__'):
                raise ValueError('Refined segment order mismatch')
            intermediate = self.probe(part)
            video = next(s for s in intermediate['streams'] if s['codec_type'] == 'video')
            if int(video['nb_read_frames']) != count or (video['width'], video['height']) != (1920, 1088):
                raise ValueError('Refiner processing frame/size mismatch')
        refined = outputs[0]
        if segmented:
            refined = self.job / 'refined.txt'
            refined.write_text(''.join(f"file 'refined/{part.name}'\n" for part in outputs))
        self.run(final_command(refined, frames, spec['width'], spec['height'], spec['has_audio'], concat=segmented))
        media = self.probe(self.job / 'output.mp4')
        videos = [s for s in media['streams'] if s['codec_type'] == 'video']
        audios = [s for s in media['streams'] if s['codec_type'] == 'audio']
        if len(videos) != 1 or len(audios) != int(spec['has_audio']):
            raise ValueError('Output stream mismatch')
        video = videos[0]
        if (video['width'], video['height'], int(video['nb_read_frames'])) != (1920, 1080, frames) or abs(float(rate(video['avg_frame_rate']) / fps) - 1) > 1e-6:
            raise ValueError('Output dimensions/frame mismatch')
        if video['codec_name'] != 'h264' or video['pix_fmt'] != 'yuv420p' or video.get('sample_aspect_ratio') != '1:1':
            raise ValueError('Output format mismatch')
        if abs(float(video['duration']) - float(frames / fps)) > 1e-6:
            raise ValueError('Output duration mismatch')
        if spec['has_audio'] and self.audio_hash(source) != self.audio_hash(self.job / 'output.mp4'):
            raise ValueError('Audio checksum mismatch')
        if digest(source) != original:
            raise ValueError('Source changed')
        (self.job / 'refiner-evidence.json').write_text(json.dumps({
            'recipe': RECIPE, 'frames': frames, 'processing_frames': processing, 'output_fps': float(fps),
            'segment_frames': counts,
            'source_sha256': original, 'output_sha256': digest(self.job / 'output.mp4'),
            'audio_stream_unchanged': True, 'media': media,
        }))
        print('REFINER_PHASE validated', flush=True)


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def main():
    os.umask(0o077)
    worker = Worker(json.loads(Path('/job/spec.json').read_text()))
    signal.signal(signal.SIGTERM, worker.stop)
    signal.signal(signal.SIGINT, worker.stop)
    try:
        worker.main()
    except Exception as error:
        code = 'OUTPUT_VALIDATION_FAILED' if isinstance(error, (ValueError, KeyError)) else 'INFERENCE_FAILED'
        Path('/job/worker-error.json').write_text(json.dumps({'error': code}))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
