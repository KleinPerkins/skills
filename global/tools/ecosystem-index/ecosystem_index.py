#!/usr/bin/env python3
"""Bounded ecosystem observations; explicit refresh, read-only lookup."""
import sys
sys.dont_write_bytecode = True
import argparse
from lib import Refusal, refresh, search, describe, context
from lib.contracts import encode, fail

class Parser(argparse.ArgumentParser):
    def __init__(self,*args,**kwargs):
        kwargs['allow_abbrev']=False
        super().__init__(*args,**kwargs)
    def error(self,message):
        fail('invalid_input')

def main(argv=None,stdin=None,stdout=None):
    stdout=stdout or sys.stdout.buffer
    try:
        p=Parser(add_help=True)
        sub=p.add_subparsers(dest='command',required=True,parser_class=Parser)
        r=sub.add_parser('refresh'); r.add_argument('--config',required=True); r.add_argument('--cache',required=True)
        s=sub.add_parser('search'); s.add_argument('--cache',required=True); s.add_argument('--limit',type=int,default=5)
        for name in ('describe','context'):
            parser=sub.add_parser(name); parser.add_argument('--cache',required=True); parser.add_argument('--id',required=True)
        args=p.parse_args(argv)
        if args.command=='refresh': value=refresh(args.config,args.cache)
        elif args.command=='search':
            data=(stdin or sys.stdin.buffer).read(4097)
            if len(data)>4096: fail('bound_exceeded')
            try: text=data.decode('utf-8')
            except UnicodeError: fail()
            value=search(args.cache,text,args.limit)
        elif args.command=='describe': value=describe(args.cache,args.id)
        else: value=context(args.cache,args.id)
        code=0
    except Refusal as exc:
        code=exc.exit_code
        value={'schema':'ecosystem-index/result/v1','status':'unavailable' if code==3 else 'invalid', 'reasons':[exc.code]}
    except KeyboardInterrupt:
        code=3; value={'schema':'ecosystem-index/result/v1','status':'refused','reasons':['interrupted']}
    except Exception:
        # Parser, OS and backend messages can contain source values or paths.
        code=3; value={'schema':'ecosystem-index/result/v1','status':'unavailable','reasons':['unavailable']}
    stdout.write(encode(value)); return code

if __name__=='__main__': raise SystemExit(main())
