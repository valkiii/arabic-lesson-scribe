"""Keep Windows awake while a long job runs. No-op on other platforms.

SetThreadExecutionState is per thread, so call keep_awake() on the worker thread that does the job.
"""
from __future__ import annotations

import contextlib
import logging
import sys

log = logging.getLogger(__name__)

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def _set_state(flags: int) -> int:
    if sys.platform != "win32":
        return 0
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState.restype = ctypes.c_uint
    return int(ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(flags)))


@contextlib.contextmanager
def keep_awake():
    """Prevent system sleep (display may still turn off) until the block exits."""
    try:
        _set_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    except Exception:  # noqa: BLE001
        log.warning("could not set execution state", exc_info=True)
    try:
        yield
    finally:
        try:
            _set_state(ES_CONTINUOUS)  # clears the requirement
        except Exception:  # noqa: BLE001
            pass
