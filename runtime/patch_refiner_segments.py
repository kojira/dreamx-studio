"""Reuse one model across short clips; release clip tensors between files."""
import argparse
import hashlib
from pathlib import Path

SHA = '887140968617671ec8362cc59f3aad970bc25eec6ae40c4c8905de05d43b13ef'

def patched(source):
    assert hashlib.sha256(source).hexdigest() == SHA, 'Unexpected FPS-patched source'
    text = source.decode()
    old = '        num_frames = args.num_frames'
    assert text.count(old) == 1
    text = text.replace(old, '        num_frames = 4 * ((T_pixel - 1 + 3) // 4) + 1 if args.num_frames == -2 else args.num_frames')
    old = '    logging.info("[%s] Saved to %s", basename, output_path)'
    assert text.count(old) == 1
    text = text.replace(old, old + '''
    # Keep model weights, not the previous clip's pixels/latents/KV state.
    pipeline.kv_caches = None
    del video_tensor, lr_pixels, lr_latent, noise, sr_latent, video_out
    import gc
    gc.collect()
    torch.cuda.empty_cache()
''')
    result = text.encode()
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
