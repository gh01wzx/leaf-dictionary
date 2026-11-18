"""Back up the user's existing local database and stop only this app's instances."""
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import sqlite3
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]

def main():
    source=ROOT/'user_data'/'learning.sqlite3'
    if source.exists():
        backups=source.parent/'backups'
        backups.mkdir(exist_ok=True)
        dest=backups/('before-ai-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.sqlite3')
        reader=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)
        writer=sqlite3.connect(dest)
        try:
            reader.backup(writer)
        finally:
            writer.close(); reader.close()
        print('Existing learning database backed up before migration.',flush=True)
    for port in (49183,49185):
        base=f'http://127.0.0.1:{port}'
        try:
            with urllib.request.urlopen(base+'/api/health',timeout=3) as r:
                if json.load(r).get('app')!='leaf-offline-dictionary-v1':
                    raise RuntimeError(f'Port {port} belongs to a different application.')
            with urllib.request.urlopen(base,timeout=3) as r:
                token=re.search(r'name="leaf-token" content="([^"]+)"',r.read().decode())[1]
            req=urllib.request.Request(base+'/api/quit',data=b'{}',headers={'Content-Type':'application/json','X-Leaf-Token':token})
            with urllib.request.urlopen(req,timeout=5) as r: assert json.load(r)['ok']
            print('Stopped app instance',port,flush=True)
        except OSError:
            pass
    time.sleep(3)

if __name__=='__main__':main()
