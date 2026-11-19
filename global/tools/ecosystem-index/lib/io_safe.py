"""No-follow filesystem access and cooperative, owner-private publication."""
from __future__ import annotations
import contextlib
import os
import secrets
import stat
import sys
from .contracts import Refusal, fail, absolute, encode, json_load, snapshot, SNAPSHOT_MAX

FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC


def _directory_at(parent, name):
    pin = child = None
    try:
        if sys.platform.startswith('linux'):
            path_flag = getattr(os, 'O_PATH', None)
            if path_flag is None: fail('unavailable',3)
            # Do not combine O_DIRECTORY with O_NOFOLLOW on a named component:
            # some Linux emulators follow that pair's final directory symlink.
            # O_PATH pins the object without opening it for I/O; reject links
            # and special files before reopening only the verified directory.
            pin = os.open(name, path_flag | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            pinned = os.fstat(pin)
            if not stat.S_ISDIR(pinned.st_mode) or pinned.st_uid not in {0,os.getuid()}:
                fail('unsafe_path',3)
            child = os.open('.', FLAGS | os.O_DIRECTORY, dir_fd=pin)
        else:
            child = os.open(name, FLAGS | os.O_DIRECTORY, dir_fd=parent)
        opened = os.fstat(child)
        if not stat.S_ISDIR(opened.st_mode) or opened.st_uid not in {0,os.getuid()}:
            fail('unsafe_path',3)
        if pin is not None and (pinned.st_dev,pinned.st_ino) != (opened.st_dev,opened.st_ino):
            fail('unsafe_path',3)
        result = child; child = None
        return result
    finally:
        if child is not None: os.close(child)
        if pin is not None: os.close(pin)


@contextlib.contextmanager
def directory(path):
    absolute(path)
    fd = os.open('/', FLAGS | os.O_DIRECTORY)
    try:
        for component in path.split('/')[1:]:
            if not component: continue
            child = _directory_at(fd, component)
            os.close(fd); fd = child
        yield fd
    except OSError:
        fail('unsafe_path',3)
    finally:
        os.close(fd)


def read_at(fd, name, maximum, private=False):
    child = None
    try:
        child = os.open(name, FLAGS | os.O_NONBLOCK, dir_fd=fd)
        st = os.fstat(child)
        if not stat.S_ISREG(st.st_mode): fail('unsafe_path',3)
        if st.st_uid != os.getuid(): fail('unsafe_path',3)
        if private and stat.S_IMODE(st.st_mode) != 0o600: fail('unsafe_path',3)
        if st.st_size > maximum: fail('bound_exceeded',3)
        chunks=[]; total=0
        while True:
            chunk=os.read(child,min(65536,maximum+1-total))
            if not chunk: break
            total += len(chunk)
            if total > maximum: fail('bound_exceeded',3)
            chunks.append(chunk)
        return b''.join(chunks)
    except OSError:
        fail('unavailable',3)
    finally:
        if child is not None: os.close(child)


def read_file(path, maximum, private=False):
    absolute(path)
    parent,name=os.path.split(path)
    with directory(parent) as fd:
        if private: private_dir(fd)
        return read_at(fd,name,maximum,private)


def private_dir(fd):
    st=os.fstat(fd)
    if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700:
        fail('unsafe_path',3)


def outside_repositories(path):
    # Only inspect lexical ancestors of the chosen state directory. Never enter
    # a repository or traverse inventory roots to decide state placement.
    with directory(path) as fd:
        pass
    current=path
    while True:
        with directory(current) as fd:
            try:
                os.stat('.git',dir_fd=fd,follow_symlinks=False)
                fail('unsafe_path',3)
            except FileNotFoundError:
                pass
        if current == '/': break
        current=os.path.dirname(current)


def load_snapshot(path):
    try:
        return snapshot(json_load(read_file(path,SNAPSHOT_MAX,True),SNAPSHOT_MAX))
    except Refusal:
        fail('unavailable',3)


class Publisher:
    """One cooperative lock. A lock is never interpreted as stale or stolen."""
    def __init__(self,path,maximum=SNAPSHOT_MAX):
        absolute(path)
        self.path=path; self.parent,self.name=os.path.split(path)
        self.maximum=maximum; self.fd=None; self.lock=None; self.temp=None
        self.lock_identity=None; self.temp_identity=None

    def __enter__(self):
        outside_repositories(self.parent)
        self.directory_context=directory(self.parent)
        self.fd=self.directory_context.__enter__()
        try:
            private_dir(self.fd)
            try:
                existing=os.stat(self.name,dir_fd=self.fd,follow_symlinks=False)
                if not stat.S_ISREG(existing.st_mode) or existing.st_uid != os.getuid() or stat.S_IMODE(existing.st_mode)!=0o600:
                    fail('unsafe_path',3)
            except FileNotFoundError: pass
            self.lock=self.name+'.lock'
            try:
                lockfd=os.open(self.lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=self.fd)
            except FileExistsError:
                fail('busy',3)
            try:
                st=os.fstat(lockfd); self.lock_identity=(st.st_dev,st.st_ino)
                os.write(lockfd,secrets.token_hex(16).encode('ascii')); os.fsync(lockfd)
            finally: os.close(lockfd)
            return self
        except BaseException:
            self.__exit__(None,None,None)
            raise

    def publish(self,value,before_replace=None):
        data=encode(snapshot(value))
        if len(data)>self.maximum: fail('bound_exceeded',3)
        self.temp='.'+self.name+'.'+secrets.token_hex(16)+'.tmp'
        tempfd=os.open(self.temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=self.fd)
        self.temp_identity=(os.fstat(tempfd).st_dev,os.fstat(tempfd).st_ino)
        try:
            with os.fdopen(tempfd,'wb') as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            readback=read_at(self.fd,self.temp,self.maximum,True)
            snapshot(json_load(readback,self.maximum))
            if data!=readback: fail('unavailable',3)
            if before_replace: before_replace()
            os.replace(self.temp,self.name,src_dir_fd=self.fd,dst_dir_fd=self.fd)
            self.temp=None
            os.fsync(self.fd)
            if read_at(self.fd,self.name,self.maximum,True)!=data: fail('unavailable',3)
            return data
        finally:
            if self.temp is not None:
                self.remove_temp()

    def remove_temp(self):
        if self.temp is not None:
            try:
                st=os.stat(self.temp,dir_fd=self.fd,follow_symlinks=False)
                if (st.st_dev,st.st_ino)==self.temp_identity: os.unlink(self.temp,dir_fd=self.fd)
            except FileNotFoundError: pass
            self.temp=None; self.temp_identity=None

    def __exit__(self,*_):
        if self.fd is not None:
            if self.temp: self.remove_temp()
            if self.lock_identity:
                try:
                    st=os.stat(self.lock,dir_fd=self.fd,follow_symlinks=False)
                    if (st.st_dev,st.st_ino)==self.lock_identity: os.unlink(self.lock,dir_fd=self.fd)
                except FileNotFoundError: pass
            self.directory_context.__exit__(None,None,None)
            self.fd=None
