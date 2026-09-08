"""Host-runner CPU validation lifecycle using the shared persistent operation lease."""
import json
import os
import re
import threading
import time

from .docker_control import execute, inspect_job, kill_job
from .jobs import Busy
from .video_container import VALIDATION_SECONDS, validation_command, verify_validator, video_paths
from .video_contract import number, padded_frames, output_rate


class ValidationFailure(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class VideoValidation:
    def __init__(self, app, jobs, lock, image_id, status):
        self.app, self.jobs, self.lock = app, jobs, lock
        self.image_id, self.status = image_id, status
        self.cancel_event = None

    def cancel(self, input_id):
        with self.lock:
            operation = self.jobs.operation()
            if operation and operation['kind'] == 'validate_video' and operation['owner_id'] == input_id:
                if self.cancel_event is not None:
                    self.cancel_event.set()
                return {'state': 'cancelling'}
            return {'state': self.jobs.video(input_id)['state']}

    def validate(self, input_id, output_fps=24):
        output_fps = float(output_rate(output_fps))
        with self.lock:
            availability = self.status()
            if availability.get('reason') == 'BUSY':
                raise Busy('BUSY')
            if not self.image_id or not availability.get('runtime_ready'):
                raise ValidationFailure('RUNNER_NOT_READY')
            self.jobs.reserve_validation(input_id)
            cancelled = threading.Event()
            self.cancel_event = cancelled
        cid = None
        stopped = False
        result = None
        failure = 'INVALID_VIDEO'
        try:
            user = f'{os.getuid()}:{os.getgid()}'
            arguments, mounts = validation_command(self.app, input_id, self.image_id, user, output_fps)
            cid = execute(arguments).strip()
            # Persist identity before start so a runner restart cannot release a
            # live CPU validator merely because GPU active.json is empty.
            self.jobs.bind_container(input_id, cid)
            verify_validator(inspect_job(cid, input_id), input_id=input_id,
                             expected_image_id=self.image_id, expected_mounts=mounts,
                             expected_user=user)
            deadline = time.monotonic() + VALIDATION_SECONDS
            if cancelled.is_set():
                raise ValidationFailure('VALIDATION_CANCELLED')
            execute(['start', cid])
            while True:
                container = inspect_job(cid, input_id)
                if not container['State']['Running']:
                    stopped = True
                    break
                if cancelled.is_set():
                    raise ValidationFailure('VALIDATION_CANCELLED')
                if time.monotonic() >= deadline:
                    raise ValidationFailure('VALIDATION_TIMEOUT')
                time.sleep(0.1)
            if cancelled.is_set():
                raise ValidationFailure('VALIDATION_CANCELLED')
            if container['State'].get('OOMKilled'):
                raise ValidationFailure('INVALID_VIDEO')
            _, work = video_paths(self.app, input_id)
            receipt, normalized = work / 'result.json', work / 'normalized.mp4'
            if receipt.is_symlink() or not receipt.is_file() or receipt.stat().st_size > 16384:
                raise ValidationFailure('INVALID_VIDEO')
            result = json.loads(receipt.read_text())
            if container['State']['ExitCode'] != 0 or 'error' in result:
                code = result.get('error')
                if code not in ('INVALID_VIDEO', 'UNSUPPORTED_VIDEO', 'INVALID_DURATION', 'UNSUPPORTED_AUDIO_TIMING'):
                    code = 'INVALID_VIDEO'
                raise ValidationFailure(code)
            if normalized.is_symlink() or not normalized.is_file() or not normalized.stat().st_size:
                raise ValidationFailure('INVALID_VIDEO')
            metadata = result['metadata']
            padded_frames(metadata['normalized_frames'])
            for field in ('width', 'height'):
                if type(metadata[field]) is not int or metadata[field] <= 0:
                    raise ValidationFailure('INVALID_VIDEO')
            if number(metadata['duration_seconds']) <= 0:
                raise ValidationFailure('INVALID_VIDEO')
            if type(metadata['has_audio']) is not bool or metadata.get('normalized_fps') != output_fps:
                raise ValidationFailure('INVALID_VIDEO')
            if any(not re.fullmatch('[0-9a-f]{64}', metadata[key]) for key in ('raw_sha256', 'normalized_sha256')):
                raise ValidationFailure('INVALID_VIDEO')
            self.jobs.finish_video(input_id, metadata)
            result = {key: metadata[key] for key in ('width', 'height', 'duration_seconds', 'source_fps',
                                                    'normalized_frames', 'has_audio')}
            result.update(input_id=input_id, normalized_fps=output_fps)
        except ValidationFailure as error:
            failure = error.code
            result = None
        except Exception:
            result = None
        finally:
            if cid is None:
                stopped = True  # No start command has been issued.
            elif not stopped:
                try:
                    kill_job(cid, input_id)
                    stopped = not inspect_job(cid, input_id)['State']['Running']
                except Exception:
                    stopped = False
            if result is None:
                self.jobs.fail_video(input_id)
            if stopped:
                with self.lock:
                    self.jobs.release_stopped(input_id)
                    self.cancel_event = None
            else:
                failure = 'STOP_UNCONFIRMED'
                result = None
        if result is None:
            raise ValidationFailure(failure)
        return result
