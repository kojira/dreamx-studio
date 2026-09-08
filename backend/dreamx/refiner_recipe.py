"""Fixed, user-independent argv for the approved Refiner1080 recipe."""
from .video_contract import output_geometry, padded_frames, output_rate

PROMPT = ('Cinematic, High Contrast, highly detailed, taken using a Canon EOS R camera, '
          'hyper detailed photo-realistic maximum detail, Color Grading, ultra HD, '
          'extreme meticulous detailing, skin pore detailing, hyper sharpness, '
          'perfect without deformations')


def segment_counts(frames, fps):
    padded_frames(frames)
    size = max(1, int(5 * output_rate(fps)))
    return [min(size, frames - start) for start in range(0, frames, size)]


def split_command(frames, fps):
    counts = segment_counts(frames, fps)
    boundaries = ','.join(str(n) for n in range(counts[0], frames, counts[0]))
    return ['ffmpeg', '-nostdin', '-n', '-v', 'error', '-i', '/input.mp4',
            '-map', '0:v:0', '-an', '-c:v', 'libx264', '-crf', '0', '-preset', 'ultrafast',
            '-bf', '0', '-g', str(counts[0]), '-keyint_min', str(counts[0]), '-sc_threshold', '0',
            '-f', 'segment', '-segment_frames', boundaries, '-reset_timestamps', '1',
            '/job/chunks/%06d.mp4']


def inference_command(frames, segmented=False):
    return ['python', 'inference_sr.py', '--config_path', 'configs/sr_dit_5b.yaml',
            '--checkpoint_path', '/opt/dreamx/checkpoints/refiner/sr_dit_5b.pt',
            '--input_path', '/job/chunks' if segmented else '/input.mp4', '--output_folder', '/job/refined',
            '--prompt', PROMPT, '--sigma_start', '0.6251',
            '--num_frames', '-2' if segmented else str(padded_frames(frames)), '--target_size', '1088', '1920',
            '--causal', '--seed', '42', '--kv_len', '9',
            '--latent_upsampler_config', 'configs/latent_upsampler_flash.yaml',
            '--latent_upsampler_ckpt', '/opt/dreamx/checkpoints/refiner/latent_upsampler_flash.pt',
            '--use_window_attn', '--window_attn_impl', 'triton',
            '--window_block_hw', '4', '4', '--window_block_radius_hw', '3', '3',
            '--use_lq_anchor', '--lq_guidance_mode', 'v', '--lq_guidance_scale', '1.0',
            '--lq_anchor_align', 'frame', '--no-keep_audio']


def final_command(refined, frames, width, height, has_audio, concat=False):
    padded_frames(frames)
    w, h, x, y = output_geometry(width, height)
    # trim only the added processing frames. A global -frames:v/-shortest can
    # terminate muxing before all copied AAC packets have been consumed.
    filters = (f'trim=end_frame={frames},setpts=PTS-STARTPTS,'
               f'scale={w}:{h}:flags=lanczos,pad=1920:1080:{x}:{y},setsar=1')
    args = ['ffmpeg', '-nostdin', '-n', '-v', 'error']
    if concat:
        args += ['-f', 'concat', '-safe', '0']
    args += ['-i', str(refined),
            '-i', '/input.mp4', '-map', '0:v:0']
    if has_audio:
        args += ['-map', '1:a:0', '-c:a', 'copy']
    args += ['-vf', filters, '-c:v', 'libx264', '-crf', '18', '-preset', 'fast',
             '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '/job/output.mp4']
    return args
