"""Exact CPU validator container policy, separate from uncapped GPU workers."""
import re
from pathlib import Path

from .docker_control import LABEL
from .paths import id_path
from .safety import GIB
from .video_contract import output_rate

VALIDATION_SECONDS = 60
OPERATION_LABEL = 'org.dreamx.studio.operation'


def video_paths(app: Path, input_id: str):
    directory = id_path(app / 'video-inputs', input_id)
    raw = directory / 'raw.mp4'
    work = directory / 'work'
    for path in (raw, work):
        if path.is_symlink() or path.resolve().parent != directory.resolve():
            raise ValueError('Invalid resource path')
    return raw, work


def validation_command(app, input_id, image_id, user, output_fps=24):
    """Return create argv and exact allowed mounts; no user argv or filenames."""
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id):
        raise ValueError('Expected pinned validator image')
    if not re.fullmatch(r'[1-9][0-9]*:[1-9][0-9]*', user):
        raise ValueError('Expected explicit non-root UID:GID')
    raw, work = video_paths(app, input_id)
    if not raw.is_file() or not work.is_dir():
        raise ValueError('Reserved input missing')
    mounts = [('bind', str(raw), '/input.mp4', False),
              ('bind', str(work), '/work', True)]
    args = ['create', '--name', 'dreamx-validate-' + input_id,
            '--label', LABEL + '=' + input_id,
            '--label', OPERATION_LABEL + '=validate_video',
            '--restart', 'no', '--memory', str(2 * GIB),
            '--memory-swap', str(2 * GIB), '--cpus', '2', '--pids-limit', '128',
            '--network', 'none', '--read-only', '--user', user,
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--env', 'PYTHONDONTWRITEBYTECODE=1',
            '--log-opt', 'max-size=10m', '--log-opt', 'max-file=3']
    for typ, src, dest, writable in mounts:
        args += ['--mount', f'type={typ},src={src},dst={dest}' + ('' if writable else ',readonly')]
    args += ['--env', 'DREAMX_OUTPUT_FPS=' + str(float(output_rate(output_fps))), image_id]
    return args, mounts


def verify_validator(c, *, input_id, expected_image_id, expected_mounts, expected_user):
    """Verify Docker's effective configuration before starting the demuxer."""
    config, host = c['Config'], c['HostConfig']
    labels = config.get('Labels', {})
    if labels.get(LABEL) != input_id or labels.get(OPERATION_LABEL) != 'validate_video':
        raise ValueError('Validation ownership mismatch')
    if c['Image'] != expected_image_id:
        raise ValueError('Validator image mismatch')
    if config['User'] != expected_user or not re.fullmatch(r'[1-9][0-9]*:[1-9][0-9]*', expected_user):
        raise ValueError('Expected explicit non-root UID:GID')
    if host['Memory'] != 2 * GIB or host['MemorySwap'] != 2 * GIB:
        raise ValueError('Invalid CPU memory/swap policy')
    if host.get('NanoCpus') != 2_000_000_000 or host.get('PidsLimit') != 128:
        raise ValueError('Invalid CPU/process limits')
    if host.get('Privileged') or host.get('PidMode') == 'host' or host.get('IpcMode') == 'host':
        raise ValueError('Unsafe validator namespace')
    if host.get('Devices') or host.get('DeviceRequests'):
        raise ValueError('Validator must not have GPU/device access')
    if host.get('NetworkMode') != 'none' or not host.get('ReadonlyRootfs'):
        raise ValueError('Validator isolation missing')
    if host['RestartPolicy']['Name'] != 'no':
        raise ValueError('Unexpected restart policy')
    if host.get('CapDrop') != ['ALL'] or host.get('CapAdd') or 'no-new-privileges' not in host.get('SecurityOpt', []):
        raise ValueError('Validator security constraints missing')
    mounts = sorted((v['Type'], v['Source'], v['Destination'], v['RW']) for v in c['Mounts'])
    if mounts != sorted(expected_mounts):
        raise ValueError('Validator mount mismatch')
