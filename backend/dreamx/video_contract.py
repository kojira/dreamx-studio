"""Pure v2 media contracts; parsing never launches host FFmpeg."""
import math
from fractions import Fraction

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
OUTPUT_FPS = 24
RECIPE = 'refiner1080-v2'
SEED = 42


class InvalidVideo(ValueError):
    def __init__(self, code='INVALID_VIDEO'):
        self.code = code
        super().__init__(code)


def number(value):
    try:
        result = float(value)
        if not math.isfinite(result):
            raise ValueError
        return result
    except (TypeError, ValueError, OverflowError):
        raise InvalidVideo() from None


def rate(value):
    try:
        result = Fraction(value)
        if result <= 0:
            raise ValueError
        return result
    except (ValueError, TypeError, ZeroDivisionError):
        raise InvalidVideo() from None


def output_rate(value):
    return rate(str(number(value)))


def padded_frames(frames):
    if type(frames) is not int or frames < 1:
        raise InvalidVideo('INVALID_DURATION')
    return 4 * ((frames - 1 + 3) // 4) + 1


def output_geometry(width, height):
    """Fit without cropping; yuv420p padding coordinates must be even."""
    if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
        raise InvalidVideo()
    scale = min(Fraction(1920, width), Fraction(1080, height))
    w = 2 * ((width * scale) // 2)
    h = 2 * ((height * scale) // 2)
    return int(w), int(h), int((1920 - w) // 4 * 2), int((1080 - h) // 4 * 2)


def probe_contract(probe, output_fps=OUTPUT_FPS, normalized=False):
    """Validate bounded metadata before decoding any frames.

    Full decode, MP4 data-reference checks and timestamp/CFR verification are
    additional mandatory steps in the isolated validator, not replaced here.
    """
    try:
        streams = probe['streams']
        videos = [s for s in streams if s.get('codec_type') == 'video']
        audios = [s for s in streams if s.get('codec_type') == 'audio']
        if len(videos) != 1 or len(audios) > 1 or len(streams) != len(videos) + len(audios):
            raise InvalidVideo('UNSUPPORTED_VIDEO')
        video = videos[0]
        if video['codec_name'] != 'h264' or video['pix_fmt'] != 'yuv420p':
            raise InvalidVideo('UNSUPPORTED_VIDEO')
        w, h = video['width'], video['height']
        if type(w) is not int or type(h) is not int or not (256 <= w <= 1280 and 144 <= h <= 720):
            raise InvalidVideo('UNSUPPORTED_VIDEO')
        if abs(Fraction(w, h) / Fraction(16, 9) - 1) > Fraction(1, 100):
            raise InvalidVideo('UNSUPPORTED_VIDEO')
        # Unspecified SAR in MP4 denotes square pixels; an explicit non-unit SAR
        # must not be silently repaired. Frame validation checks display matrices.
        sar = video.get('sample_aspect_ratio', '1:1')
        if sar not in ('N/A', '0:1') and rate(sar.replace(':', '/')) != 1:
            raise InvalidVideo('UNSUPPORTED_VIDEO')
        if number(video.get('tags', {}).get('rotate', 0)) != 0:
            raise InvalidVideo('UNSUPPORTED_VIDEO')
        for side in video.get('side_data_list', []):
            if number(side.get('rotation', 0)) != 0:
                raise InvalidVideo('UNSUPPORTED_VIDEO')
        fps = rate(video['avg_frame_rate'])
        if (not normalized and not 1 <= fps <= 60) or rate(video['r_frame_rate']) != fps:
            raise InvalidVideo('UNSUPPORTED_VIDEO')
        duration = number(video['duration'])
        if duration <= 0:
            raise InvalidVideo('INVALID_DURATION')
        start = number(video.get('start_time', 0))
        if audios:
            audio = audios[0]
            if audio['codec_name'] != 'aac' or audio['channels'] not in (1, 2) or not 0 < number(audio['sample_rate']) <= 48000:
                raise InvalidVideo('UNSUPPORTED_VIDEO')
            audio_start = number(audio.get('start_time', 0))
            audio_duration = number(audio['duration'])
            if audio_duration <= 0 or abs(audio_start - start) >= 1 / output_rate(output_fps) or audio_start + audio_duration - start - duration > 1 / output_rate(output_fps):
                raise InvalidVideo('UNSUPPORTED_AUDIO_TIMING')
        return {'width': w, 'height': h, 'duration_seconds': duration,
                'source_fps': float(fps), 'has_audio': bool(audios)}
    except (KeyError, TypeError, AttributeError, IndexError):
        raise InvalidVideo() from None


def normalized_contract(probe, source, output_fps=OUTPUT_FPS):
    output_fps = output_rate(output_fps)
    metadata = probe_contract(probe, output_fps, normalized=True)
    video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    if rate(video['avg_frame_rate']) != output_fps:
        raise InvalidVideo('INVALID_VIDEO')
    try:
        frames = int(video['nb_read_frames'])
    except (KeyError, TypeError, ValueError):
        raise InvalidVideo() from None
    padded_frames(frames)
    if abs(frames / output_fps - source['duration_seconds']) > 1 / output_fps + 1e-9:
        raise InvalidVideo('INVALID_DURATION')
    if metadata['has_audio'] != source['has_audio']:
        raise InvalidVideo('INVALID_VIDEO')
    return frames
