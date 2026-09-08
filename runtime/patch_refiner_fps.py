"""Avoid torchvision.write_video rounding a float fps to an integer."""
import argparse
import hashlib
from pathlib import Path

SHA = 'cb146f455a515e0309927cde07d062206a8e7f014aa3d409a2697bb3d78ccd66'

def patched(source):
    assert hashlib.sha256(source).hexdigest() == SHA, 'Unexpected audio-patched upstream source'
    old = '    write_video(output_path, video_out, fps=fps)'
    text = source.decode()
    assert text.count(old) == 1
    result = text.replace(old, '    from fractions import Fraction\n    write_video(output_path, video_out, fps=Fraction(str(fps)))').encode()
    compile(result, 'inference_sr.py', 'exec')
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = patched(args.source.read_bytes())
    with args.output.open('xb') as target:
        target.write(result)
    print(hashlib.sha256(result).hexdigest())
