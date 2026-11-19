"""Generic shipped-data and local installer preservation contracts.

The data-only contract can be run against a reviewed source directory through
DOC_STYLE_SOURCE_DIR. Tests never print captured reference/style values. All
installer tests use this current test package and isolated private destinations.
"""
from pathlib import Path
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
SOURCE=Path(os.environ.get('DOC_STYLE_SOURCE_DIR',str(HERE)))

def read(path):return json.loads(path.read_bytes())
def fact(path):
    info=path.lstat()
    return (path.read_bytes(),info.st_ino,info.st_mode,info.st_mtime_ns,info.st_ctime_ns)

class ShippedData(unittest.TestCase):
    def test_both_profiles_are_generic_unbound_starters(self):
        for relative,name in (('templates/blank-style-profile.json','blank-style-profile'),('profiles/laurence/default.json','default')):
            with self.subTest(profile=name):
                value=read(SOURCE/relative)
                self.assertTrue(value.get('schema')==1 and value.get('name')==name,'source identity/schema differs')
                self.assertTrue(value.get('source_doc_id') is None,'shipped source reference must be empty')
                self.assertTrue(value.get('template_doc_id') is None,'shipped template reference must be empty')
                self.assertTrue(value.get('named_styles')=={},'shipped named styles must be empty')
                self.assertTrue(set(value)<= {'schema','name','description','named_styles','document_style','source_doc_id','template_doc_id'},'captured profile fields must not be shipped')
                if name=='default':self.assertTrue(value.get('document_style')=={},'Laurence starter must not ship captured document style')

class Install(unittest.TestCase):
    def invoke(self,home,config,*args,env_config=None):
        env={'HOME':str(home),'PATH':str(Path(sys.executable).parent)+os.pathsep+os.defpath,
             'LANG':'C','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'}
        if env_config is not None:env['GOOGLE_KIT_CONFIG_DIR']=str(env_config)
        command=['/bin/bash',str(HERE/'install.sh')]
        if config is not None:command+=['--config-dir',str(config)]
        result=subprocess.run([*command,*args],env=env,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        return result.stdout

    def test_dry_run_does_not_create_the_destination(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);config=root/'not-created'
            text=self.invoke(root,config,'--dry-run','--no-repair')
            self.assertFalse(config.exists());self.assertEqual(text.count('would seed:'),2)

    def test_fresh_install_writes_only_two_generic_private_profiles(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);config=root/'config';self.invoke(root,config,'--no-repair');profiles=config/'doc-styles'
            self.assertEqual({p.name for p in profiles.iterdir()},{'blank-style-profile.json','default.json'})
            self.assertEqual(stat.S_IMODE(profiles.stat().st_mode),0o700)
            for name in ('blank-style-profile','default'):
                path=profiles/(name+'.json');value=read(path)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
                self.assertEqual(value['name'],name);self.assertIsNone(value['source_doc_id']);self.assertIsNone(value['template_doc_id'])
                self.assertEqual(value['named_styles'],{})

    def test_existing_valid_local_profile_and_identity_are_preserved(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);config=root/'config';self.invoke(root,config,'--no-repair')
            path=config/'doc-styles/default.json';value=read(path);value['named_styles']={'SYNTHETIC_LOCAL':{'custom':True}}
            path.write_text(json.dumps(value,indent=1)+'\n');before=fact(path)
            text=self.invoke(root,config,'--no-repair')
            self.assertEqual(fact(path),before);self.assertIn('present:',text)

    def test_no_repair_preserves_invalid_existing_bytes_and_inode(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);config=root/'config';self.invoke(root,config,'--no-repair')
            path=config/'doc-styles/default.json';path.write_text('synthetic invalid JSON');before=fact(path)
            text=self.invoke(root,config,'--no-repair')
            self.assertEqual(fact(path),before);self.assertIn('left unchanged',text)
            self.assertFalse(list(path.parent.glob('*.quarantine-*')))

    def test_template_only_does_not_install_a_default(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);config=root/'config';self.invoke(root,config,'--template-only','--no-repair')
            self.assertEqual([p.name for p in (config/'doc-styles').iterdir()],['blank-style-profile.json'])

    def test_explicit_directory_precedes_environment_without_touching_it(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);chosen=root/'chosen';unused=root/'not-used'
            self.invoke(root,chosen,'--no-repair',env_config=unused)
            self.assertTrue((chosen/'doc-styles/default.json').is_file());self.assertFalse(unused.exists())

    def test_installer_preserves_its_source_files(self):
        paths=[HERE/'install.sh',HERE/'templates/blank-style-profile.json',HERE/'profiles/laurence/default.json']
        before={str(path):fact(path) for path in paths}
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);self.invoke(root,root/'config','--no-repair')
        self.assertEqual({str(path):fact(path) for path in paths},before)

if __name__=='__main__':unittest.main()
