"""Directory-reference refusal, replacement-race and descriptor-lifetime checks."""
import errno
import os
from pathlib import Path
import stat
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lib import io_safe
from lib.contracts import Refusal
import test_index


class DirectoryReferenceContract(unittest.TestCase):
    # A synthetic flag exercises Linux control flow on macOS, without pretending
    # to execute Linux syscalls. Real Linux filesystem cases below remain gated.
    path_flag=1 << 28

    def exercise(self, fault=None, pin_kind=stat.S_IFDIR, child_kind=stat.S_IFDIR,
                 pin_owner=None, child_owner=None, child_inode=7):
        acquired=[]; closed=[]; calls=[]
        owner=os.getuid()
        pin_stat=SimpleNamespace(st_mode=pin_kind|0o700,st_uid=owner if pin_owner is None else pin_owner,
                                 st_dev=1,st_ino=7)
        child_stat=SimpleNamespace(st_mode=child_kind|0o700,st_uid=owner if child_owner is None else child_owner,
                                   st_dev=1,st_ino=child_inode)
        def open_at(name,flags,*,dir_fd):
            calls.append((name,flags,dir_fd))
            if name=='component':
                self.assertEqual(dir_fd,10)
                self.assertTrue(flags & self.path_flag)
                self.assertTrue(flags & os.O_NOFOLLOW)
                self.assertFalse(flags & os.O_DIRECTORY)
                result=11
            else:
                self.assertEqual(name,'.'); self.assertEqual(dir_fd,11)
                if fault=='reopen': raise OSError(errno.EACCES,'synthetic')
                result=12
            acquired.append(result); return result
        def fstat(fd):
            if fault==('pin_stat' if fd==11 else 'child_stat'):
                raise OSError(errno.EIO,'synthetic')
            return pin_stat if fd==11 else child_stat
        result=None; failure=None
        with patch.object(io_safe.sys,'platform','linux'), \
             patch.object(os,'O_PATH',self.path_flag,create=True), \
             patch('os.open',side_effect=open_at),patch('os.fstat',side_effect=fstat), \
             patch('os.close',side_effect=closed.append):
            try: result=io_safe._directory_at(10,'component')
            except (OSError,Refusal) as exc: failure=exc
        self.assertEqual(len(closed),len(set(closed)))
        self.assertEqual(set(closed),set(acquired)-({result} if result is not None else set()))
        return result,failure,calls,closed

    def test_valid_reference_returns_readable_child_and_closes_pin(self):
        result,failure,calls,closed=self.exercise()
        self.assertEqual(result,12); self.assertIsNone(failure); self.assertEqual(closed,[11])

    def test_symlink_regular_fifo_refused_before_io_reopen(self):
        for kind in (stat.S_IFLNK,stat.S_IFREG,stat.S_IFIFO):
            with self.subTest(kind=kind):
                result,failure,calls,closed=self.exercise(pin_kind=kind)
                self.assertIsInstance(failure,Refusal); self.assertIsNone(result)
                self.assertEqual(len(calls),1); self.assertEqual(closed,[11])

    def test_foreign_owner_refused_before_reopen(self):
        result,failure,calls,closed=self.exercise(pin_owner=os.getuid()+10000)
        self.assertIsInstance(failure,Refusal); self.assertEqual(len(calls),1)

    def test_all_acquired_descriptors_close_on_stat_or_reopen_failure(self):
        for fault in ('pin_stat','reopen','child_stat'):
            with self.subTest(fault=fault):
                result,failure,calls,closed=self.exercise(fault=fault)
                self.assertIsInstance(failure,OSError); self.assertIsNone(result)

    def test_changed_child_identity_type_or_owner_refuses_and_closes_both(self):
        for kwargs in ({'child_inode':8},{'child_kind':stat.S_IFREG},{'child_owner':os.getuid()+10000}):
            with self.subTest(kwargs=kwargs):
                result,failure,calls,closed=self.exercise(**kwargs)
                self.assertIsInstance(failure,Refusal); self.assertEqual(closed,[12,11])

    def test_missing_linux_path_reference_refuses_without_fallback(self):
        with patch.object(io_safe.sys,'platform','linux'),patch.object(os,'O_PATH',None,create=True), \
             patch('os.open') as opened:
            with self.assertRaises(Refusal): io_safe._directory_at(10,'component')
            opened.assert_not_called()

    def test_context_body_failure_closes_every_directory(self):
        acquired=[]; closed=[]; real_open=os.open; real_close=os.close
        def open_at(*args,**kwargs):
            fd=real_open(*args,**kwargs); acquired.append(fd); return fd
        def close(fd): closed.append(fd); return real_close(fd)
        with patch('os.open',side_effect=open_at),patch('os.close',side_effect=close):
            with self.assertRaisesRegex(RuntimeError,'synthetic'):
                with io_safe.directory(str(Path(__file__).resolve().parent)):
                    raise RuntimeError('synthetic')
        self.assertCountEqual(acquired,closed)


@unittest.skipUnless(sys.platform.startswith('linux') and hasattr(os,'O_PATH'),
                     'requires actual Linux path-reference syscalls')
class LinuxDirectoryTraversal(test_index.Fixture):
    def test_regular_and_fifo_components_never_receive_io_open(self):
        for kind in ('regular','fifo'):
            with self.subTest(kind=kind):
                component=self.root/kind
                if kind=='fifo': os.mkfifo(component)
                else: component.write_bytes(b'synthetic')
                seen=[]; real=os.open
                def opened(name,flags,*args,**kwargs):
                    if os.fspath(name)==kind:
                        seen.append(flags)
                        self.assertTrue(flags & os.O_PATH)
                        self.assertFalse(flags & os.O_DIRECTORY)
                    return real(name,flags,*args,**kwargs)
                with patch('os.open',side_effect=opened),self.assertRaises(Refusal):
                    with io_safe.directory(str(component)): self.fail('non-directory accepted')
                self.assertEqual(len(seen),1)

    def test_replacement_before_pin_refuses_link_without_target_access(self):
        checked=self.root/'checked'; checked.mkdir()
        outside=self.base/'outside'; outside.mkdir(); (outside/'canary').write_bytes(b'forbidden')
        real=os.open; swapped=False; target_attempts=[]
        def opened(name,flags,*args,**kwargs):
            nonlocal swapped
            if name=='canary': target_attempts.append(name)
            if name=='checked' and flags & os.O_PATH and not swapped:
                checked.rename(self.root/'original'); checked.symlink_to(outside,target_is_directory=True); swapped=True
            return real(name,flags,*args,**kwargs)
        with patch('os.open',side_effect=opened),self.assertRaises(Refusal):
            io_safe.read_file(str(checked/'canary'),100)
        self.assertTrue(swapped); self.assertEqual(target_attempts,[])

    def test_replacement_after_pin_cannot_redirect_dot_reopen(self):
        checked=self.root/'checked'; checked.mkdir(); (checked/'canary').write_bytes(b'permitted')
        outside=self.base/'outside'; outside.mkdir(); forbidden=outside/'canary'; forbidden.write_bytes(b'forbidden')
        target=(forbidden.stat().st_dev,forbidden.stat().st_ino)
        real=os.open; swapped=False; target_opens=[]
        def opened(name,flags,*args,**kwargs):
            nonlocal swapped
            fd=real(name,flags,*args,**kwargs)
            st=os.fstat(fd)
            if (st.st_dev,st.st_ino)==target: target_opens.append(name)
            if name=='checked' and flags & os.O_PATH and not swapped:
                checked.rename(self.root/'original'); checked.symlink_to(outside,target_is_directory=True); swapped=True
            return fd
        with patch('os.open',side_effect=opened):
            self.assertEqual(io_safe.read_file(str(checked/'canary'),100),b'permitted')
        self.assertTrue(swapped); self.assertEqual(target_opens,[])

    def test_state_symlink_refuses_before_config_target_open(self):
        original=self.base/'original-state'; self.state.rename(original)
        self.state.symlink_to(original,target_is_directory=True)
        real=os.open; config_attempts=[]
        def opened(name,flags,*args,**kwargs):
            if name=='config.json': config_attempts.append(name)
            return real(name,flags,*args,**kwargs)
        with patch('os.open',side_effect=opened),self.assertRaises(Refusal): self.build()
        self.assertEqual(config_attempts,[])

    def test_verified_directory_supports_fsync_and_publication(self):
        with io_safe.directory(str(self.state)) as fd: os.fsync(fd)
        self.assertEqual(self.build()['status'],'complete')
        self.assertEqual(io_safe.load_snapshot(str(self.cache))['coverage'],'complete')


if __name__=='__main__': unittest.main()
