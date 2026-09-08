"""Runs ONLY inside the bounded, networkless CPU validation container.

The host passes fixed mounts /input.mp4 and /work, never a user-supplied path.
Errors written to result.json are stable codes, not FFmpeg stderr/private paths.
"""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess

from dreamx.video_contract import (
    InvalidVideo, MAX_UPLOAD_BYTES, OUTPUT_FPS, normalized_contract,
    number, probe_contract, rate,
)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def self_contained_mp4(path):
    """Reject QuickTime-only files and non-self-contained MP4 data references.

    Only structural container atoms are traversed; mdat is skipped with seek.
    This check does not replace the demuxer's disabled external references.
    """
    size = path.stat().st_size
    if not 0 < size <= MAX_UPLOAD_BYTES:
        raise InvalidVideo('INVALID_VIDEO')
    count = 0
    references = 0
    compatible = False
    with path.open('rb') as source:
        def atoms(start, end, depth=0):
            nonlocal count, references, compatible
            if depth > 8:
                raise InvalidVideo()
            cursor = start
            while cursor < end:
                count += 1
                if count > 100000 or end - cursor < 8:
                    raise InvalidVideo()
                source.seek(cursor)
                length, kind = struct.unpack('>I4s', source.read(8))
                header = 8
                if length == 1:
                    if end - cursor < 16:
                        raise InvalidVideo()
                    length = struct.unpack('>Q', source.read(8))[0]
                    header = 16
                elif length == 0:
                    length = end - cursor
                if length < header or cursor + length > end:
                    raise InvalidVideo()
                body, limit = cursor + header, cursor + length
                if kind == b'ftyp' and depth == 0:
                    if length - header < 8 or length - header > 4096:
                        raise InvalidVideo()
                    data = source.read(length - header)
                    brands = [data[:4]] + [data[i:i + 4] for i in range(8, len(data), 4)]
                    allowed = {b'isom', b'mp41', b'mp42', b'avc1', b'M4V ', b'M4A '}
                    allowed.update(b'iso' + str(i).encode() for i in range(2, 10))
                    compatible = bool(set(brands) & allowed)
                elif kind in (b'moov', b'trak', b'mdia', b'minf', b'dinf'):
                    atoms(body, limit, depth + 1)
                elif kind == b'dref':
                    if limit - body < 8:
                        raise InvalidVideo()
                    source.seek(body)
                    version_flags, entries = struct.unpack('>II', source.read(8))
                    if version_flags != 0 or not 1 <= entries <= 1024:
                        raise InvalidVideo()
                    offset = body + 8
                    for _ in range(entries):
                        source.seek(offset)
                        if limit - offset < 12:
                            raise InvalidVideo()
                        entry_size, entry_type, flags = struct.unpack('>I4sI', source.read(12))
                        if entry_size < 12 or offset + entry_size > limit:
                            raise InvalidVideo()
                        if entry_type not in (b'url ', b'urn ') or flags != 1:
                            raise InvalidVideo('UNSUPPORTED_VIDEO')
                        references += 1
                        offset += entry_size
                    if offset != limit:
                        raise InvalidVideo()
                cursor = limit
        atoms(0, size)
    if not compatible or not references:
        raise InvalidVideo('UNSUPPORTED_VIDEO')


def run(arguments):
    result = subprocess.run(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=50, check=False)
    if result.returncode:
        raise InvalidVideo()
    return result.stdout


def probe(path, count=False):
    arguments = ['ffprobe', '-v', 'error', '-protocol_whitelist', 'file',
                 '-enable_drefs', '0', '-show_streams', '-show_format', '-of', 'json']
    if count:
        arguments += ['-count_frames']
    try:
        return json.loads(run(arguments + [str(path)]))
    except (ValueError, UnicodeError):
        raise InvalidVideo() from None


def decoded_frames(path, stream):
    data = json.loads(run([
        'ffprobe', '-v', 'error', '-protocol_whitelist', 'file', '-enable_drefs', '0',
        '-select_streams', 'v:0', '-show_frames', '-show_entries',
        'frame=best_effort_timestamp_time,width,height,pix_fmt:frame_side_data=rotation',
        '-of', 'json', str(path),
    ]))
    frames = data.get('frames', [])
    fps = rate(stream['avg_frame_rate'])
    if not frames or len(frames) > 180:
        raise InvalidVideo('INVALID_DURATION')
    start = number(frames[0]['best_effort_timestamp_time'])
    tick = float(rate(stream['time_base']))
    # Demuxer timebase quantization, not a frame-sized tolerance that hides VFR.
    tolerance = max(tick, 0.000002)
    if abs(start - number(stream.get('start_time', 0))) > tolerance:
        raise InvalidVideo('INVALID_VIDEO')
    for index, frame in enumerate(frames):
        if (frame.get('width'), frame.get('height'), frame.get('pix_fmt')) != (stream['width'], stream['height'], 'yuv420p'):
            raise InvalidVideo('UNSUPPORTED_VIDEO')
        if abs(number(frame['best_effort_timestamp_time']) - start - float(index / fps)) > tolerance:
            raise InvalidVideo('UNSUPPORTED_VIDEO')
        if any(number(side.get('rotation', 0)) != 0 for side in frame.get('side_data_list', [])):
            raise InvalidVideo('UNSUPPORTED_VIDEO')
    if abs(len(frames) / float(fps) - number(stream['duration'])) > tolerance:
        raise InvalidVideo('INVALID_DURATION')
    # Strict full decode promotes corrupt bitstream errors to failure. ffprobe
    # alone can exit zero after a decoder warning and is not sufficient evidence.
    run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-err_detect', 'explode',
         '-protocol_whitelist', 'file', '-enable_drefs', '0', '-threads', '2',
         '-i', str(path), '-map', '0:v:0', '-map', '0:a:0?', '-f', 'null', '-'])
    return len(frames)


def audio_hash(path):
    return run(['ffmpeg', '-nostdin', '-v', 'error', '-protocol_whitelist', 'file',
                '-enable_drefs', '0', '-i', str(path), '-map', '0:a:0', '-c:a', 'copy',
                '-f', 'hash', '-hash', 'sha256', '-']).decode().strip()


def validate(source, output):
    if source.is_symlink() or not source.is_file() or output.exists() or output.is_symlink():
        raise InvalidVideo()
    self_contained_mp4(source)
    original_probe = probe(source)
    metadata = probe_contract(original_probe)
    video = next(s for s in original_probe['streams'] if s['codec_type'] == 'video')
    original_count = decoded_frames(source, video)
    timing_stream = next((s for s in original_probe['streams'] if s['codec_type'] == 'audio'), video)
    audio_offset = -number(timing_stream.get('start_time', 0))
    arguments = ['ffmpeg', '-nostdin', '-n', '-v', 'error', '-xerror',
                 '-protocol_whitelist', 'file', '-enable_drefs', '0', '-threads', '2',
                 '-copyts', '-itsoffset', str(audio_offset),
                 '-i', str(source), '-map', '0:v:0', '-map', '0:a:0?',
                 '-vf', 'setpts=PTS-STARTPTS,fps=24,setsar=1', '-c:v', 'libx264', '-preset', 'fast',
                 '-crf', '18', '-pix_fmt', 'yuv420p', '-threads', '2', '-c:a', 'copy',
                 '-map_metadata', '-1', '-movflags', '+faststart', str(output)]
    run(arguments)
    result_probe = probe(output, count=True)
    count = normalized_contract(result_probe, metadata)
    if rate(video['avg_frame_rate']) == OUTPUT_FPS and count != original_count:
        raise InvalidVideo('INVALID_DURATION')
    if metadata['has_audio'] and audio_hash(source) != audio_hash(output):
        raise InvalidVideo('UNSUPPORTED_AUDIO_TIMING')
    return {**metadata, 'normalized_frames': count, 'normalized_fps': OUTPUT_FPS,
            'raw_sha256': sha256(source), 'normalized_sha256': sha256(output)}


def main():
    os.umask(0o077)
    try:
        result = {'metadata': validate(Path('/input.mp4'), Path('/work/normalized.mp4'))}
    except InvalidVideo as error:
        result = {'error': error.code}
    except Exception:
        result = {'error': 'INVALID_VIDEO'}
    Path('/work/result.json').write_text(json.dumps(result))
    return int('error' in result)


if __name__ == '__main__':
    raise SystemExit(main())
