"""Job-scoped guard primitives with injectable observations and process control.

A production supervisor must supply independent heartbeat/telemetry, bind the
full ID to its admitted job, and keep this loop outside the inference cgroup.
"""
import subprocess
import time
from collections.abc import Callable
from .safety import Sample, emergency, exact_container_id


def kill_container(container_id: str) -> None:
    subprocess.run(
        ['docker', 'kill', '--signal', 'KILL', exact_container_id(container_id)],
        check=True, timeout=5, capture_output=True,
    )


def guard_job(
    container_id: str,
    observe: Callable[[], Sample],
    running: Callable[[], bool],
    kill: Callable[[str], None] = kill_container,
    emit: Callable[[str], None] = lambda reason: None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> str:
    target = exact_container_id(container_id)
    deadline = clock() + 10800
    while running():
        try:
            reason = emergency(observe())
        except Exception:
            reason = 'TELEMETRY_ERROR'
        if not reason and clock() >= deadline:
            reason = 'TIME_LIMIT'
        if reason:
            # Never kill by name, prefix, process-group guess or shell expansion.
            # A failed kill must propagate: do not falsely report successful abort.
            kill(target)
            emit(reason)
            return reason
        sleep(0.25)
    return 'EXITED'
