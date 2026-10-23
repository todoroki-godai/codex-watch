#!/usr/bin/env python3
"""Measure actual Codex command/exec environment filtering without a model turn.

This process is already inside the harness sandbox: externalSandbox retains it.
A nested `codex sandbox` cannot start on this macOS host (sandbox_apply EPERM).
All Codex state and generated gh configs remain in this checkout.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import select
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.test-account-environment'
OUT.mkdir(exist_ok=True)
SHARED = Path.home()/'.config/gh/hosts.yml'
before = hashlib.sha256(SHARED.read_bytes()).hexdigest()
results = []
for pin, account in ((False,'matsukaze-minden'), (True,'matsukaze-minden'), (True,'todoroki-godai')):
    with tempfile.TemporaryDirectory(dir=OUT) as d:
        d = Path(d)
        ghdir = d/'gh'; ghdir.mkdir(mode=0o700)
        (ghdir/'hosts.yml').write_text(f'github.com:\n    users:\n        {account}:\n    user: {account}\n')
        shutil.copyfile(SHARED.with_name('config.yml'),ghdir/'config.yml')
        codex_home = d/'codex-home'; codex_home.mkdir()
        env=dict(os.environ, CODEX_HOME=str(codex_home), GH_CONFIG_DIR=str(ghdir))
        for name in ('GH_TOKEN','GITHUB_TOKEN','GH_ENTERPRISE_TOKEN','GITHUB_ENTERPRISE_TOKEN','GH_DEBUG','GH_HOST'):
            env.pop(name,None)
        command=['codex','app-server','--stdio','-c','shell_environment_policy.inherit="core"']
        if pin:
            command += ['-c', 'shell_environment_policy.set.GH_CONFIG_DIR='+json.dumps(str(ghdir))]
        with (d/'server-stderr').open('w') as stderr:
            p=subprocess.Popen(command,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr,bufsize=0)
            buffer=b''
            def rpc(identifier,method,params):
                global buffer
                p.stdin.write((json.dumps(dict(jsonrpc='2.0',id=identifier,method=method,params=params))+'\n').encode())
                p.stdin.flush()
                end=time.monotonic()+30
                while time.monotonic()<end:
                    if b'\n' not in buffer:
                        ready,_,_=select.select([p.stdout],[],[],1)
                        if not ready:
                            assert p.poll() is None, 'app-server exited'
                            continue
                        chunk=os.read(p.stdout.fileno(),65536)
                        assert chunk,'app-server closed stdout'
                        buffer+=chunk
                        continue
                    line,buffer=buffer.split(b'\n',1)
                    msg=json.loads(line)
                    if msg.get('id')==identifier:
                        assert 'error' not in msg, str(msg.get('error'))
                        return msg['result']
                raise TimeoutError(method)
            try:
                rpc(1,'initialize',{'clientInfo':{'name':'gh-env-probe','version':'1.0'}})
                p.stdin.write(b'{"jsonrpc":"2.0","method":"initialized","params":{}}\n')
                p.stdin.flush()
                result=rpc(2,'command/exec',{'command':['/bin/sh','-c',
                    'printf "GH_CONFIG_DIR=%s\\n" "${GH_CONFIG_DIR-unset}"; gh api --hostname github.com user --jq .login'],
                    'cwd':str(ROOT),'sandboxPolicy':{'type':'externalSandbox','networkAccess':'enabled'},'timeoutMs':20000})
                # Log only safe fields; never persist arbitrary output from gh.
                lines=result.get('stdout','').splitlines()
                present=bool(lines and lines[0]=='GH_CONFIG_DIR='+str(ghdir))
                login=lines[-1] if lines and re.fullmatch('[A-Za-z0-9-]{1,39}',lines[-1]) else '(invalid-or-empty)'
                entry={'pin':pin,'requested':account,'env_present':present,'login':login,'exit':result.get('exitCode')}
                print(json.dumps(entry),flush=True); results.append(entry)
                assert present == pin
                if pin: assert login == account and result['exitCode']==0
            finally:
                p.terminate()
                try:p.wait(timeout=5)
                except subprocess.TimeoutExpired:p.kill();p.wait()
assert hashlib.sha256(SHARED.read_bytes()).hexdigest()==before
(OUT/'results.json').write_text(json.dumps({'shared_hosts_sha256_before':before,'shared_hosts_sha256_after':hashlib.sha256(SHARED.read_bytes()).hexdigest(),'results':results},indent=2)+'\n')
