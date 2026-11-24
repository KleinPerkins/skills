"""POSIX main-thread refresh deadline; unsupported hosts refuse explicitly."""
import contextlib
import signal
import threading
import time
from .contracts import fail

@contextlib.contextmanager
def deadline(seconds):
    if threading.current_thread() is not threading.main_thread() or not hasattr(signal,'setitimer'):
        fail('unavailable',3)
    previous=signal.getsignal(signal.SIGALRM)
    if signal.getitimer(signal.ITIMER_REAL)!=(0.0,0.0):
        fail('unavailable',3)
    def expire(*_): fail('bound_exceeded',3)
    signal.signal(signal.SIGALRM,expire)
    signal.setitimer(signal.ITIMER_REAL,seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,previous)


def tighten(seconds):
    remaining,interval=signal.getitimer(signal.ITIMER_REAL)
    signal.setitimer(signal.ITIMER_REAL,max(0.000001,min(remaining,seconds)),interval)


@contextlib.contextmanager
def bound_until(expires):
    """Use the tighter admitted operation deadline and restore the refresh budget."""
    start = time.monotonic()
    remaining, interval = signal.getitimer(signal.ITIMER_REAL)
    if remaining <= 0 or interval:
        fail("unavailable", 3)
    if expires <= start:
        fail("bound_exceeded", 3)
    signal.setitimer(signal.ITIMER_REAL, min(remaining, expires - start))
    try:
        yield
    finally:
        elapsed = time.monotonic() - start
        signal.setitimer(signal.ITIMER_REAL, max(0.000001, remaining - elapsed))
