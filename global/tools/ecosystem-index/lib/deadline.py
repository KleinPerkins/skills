"""POSIX main-thread refresh deadline; unsupported hosts refuse explicitly."""
import contextlib
import signal
import threading
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
