"""Pure resource policies. No process control or model allocation in this module."""
from dataclasses import dataclass
import math
import re

GIB = 1024 ** 3

@dataclass(frozen=True)
class Sample:
    available: int
    disk_free: int
    worker_memory: int | None
    guardian_age: float


def admission(sample: Sample, *, runtime_ready: bool, active: bool) -> str | None:
    if active:
        return "BUSY"
    if not runtime_ready:
        return "RUNTIME_NOT_READY"
    if not math.isfinite(sample.guardian_age) or not 0 <= sample.guardian_age < 2:
        return "GUARDIAN_UNAVAILABLE"
    if sample.available < 96 * GIB:
        return "INSUFFICIENT_MEMORY"
    if sample.disk_free < 150 * GIB:
        return "INSUFFICIENT_DISK"
    return None


def emergency(sample: Sample) -> str | None:
    if not math.isfinite(sample.guardian_age) or not 0 <= sample.guardian_age <= 2:
        return "GUARDIAN_LOST"
    if sample.available < 24 * GIB:
        return "HOST_MEMORY_GUARD"
    if sample.worker_memory is None or sample.worker_memory < 0:
        return "WORKER_TELEMETRY_LOST"
    if sample.worker_memory >= 72 * GIB:
        return "WORKER_MEMORY_GUARD"
    return None


def exact_container_id(value: str) -> str:
    """Reject names, shortened IDs, options and shell fragments for kill targets."""
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("Expected a full Docker container ID")
    return value


def memory_available(meminfo: str) -> int:
    for line in meminfo.splitlines():
        fields = line.split()
        if fields and fields[0] == "MemAvailable:":
            if len(fields) != 3 or fields[2] != "kB":
                raise ValueError("Invalid MemAvailable units")
            result = int(fields[1]) * 1024
            if result < 0:
                raise ValueError("Negative MemAvailable")
            return result
    raise ValueError("MemAvailable unavailable; fail closed")
