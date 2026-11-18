"""Read-only verification through the actual packaged app, after the import."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reviews/words-import-2026-11-02'
BASE='http://127.0.0.1:49183'

def main():
    for _ in range(40):
        try:
            with urllib.request.urlopen(BASE+'/api/info',timeout=2) as response:info=json.load(response)
            assert info['version']=='0.9.1'
            break
        except OSError:time.sleep(.2)
    else:raise RuntimeError('Leaf 0.9.1 did not start')
    with urllib.request.urlopen(BASE) as response:
        token=re.search(r'name="leaf-token" content="([^"]+)"',response.read().decode())[1]
    def api(path,data=None):
        req=urllib.request.Request(BASE+'/api/'+path,data=json.dumps(data).encode() if data is not None else None,
            headers={'Content-Type':'application/json','X-Leaf-Token':token})
        with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
    definitions=json.loads((OUT/'definitions.json').read_text(encoding='utf-8'))
    exported=api('export')
    assert len(exported['cards'])==len(definitions)==911
    assert {row['word']:row['meaning'] for row in exported['definition_overrides']}==definitions
    assert {row['word']:row['meaning'] for row in api('library?compact=1')['cards']}==definitions
    for word,meaning in definitions.items():
        result=api('explain',{'query':word,'save':False})
        assert result['found'] and result['can_save'],word
        assert result['explanation']['core_meaning']==meaning,word
        assert result['explanation']['custom_definition'],word
        assert not result['explanation'].get('warning'),word
        assert result['saved_card']['word']==word,word
    review=api('review')['card']
    if review:
        assert review['meaning']==definitions[review['word']]
        assert review['definition']['core_meaning']==definitions[review['word']]
    backup=max((ROOT/'user_data/backups').glob('before-reviewed-words-import-*.sqlite3'),key=lambda path:path.stat().st_mtime)
    with sqlite3.connect(backup.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        current={row['id']:row for row in exported['cards']}
        original=[dict(row) for row in db.execute('SELECT * FROM cards')]
        for row in original:assert current[row['id']]==row,('Old record changed',row['word'])
        for table in ('reviews','encounters'):
            assert exported[table]==[dict(row) for row in db.execute('SELECT * FROM '+table)],table
    assert api('stats')['total']==911
    source=Path.home()/'Desktop'/'words.md'
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    assert hashlib.sha256(source.read_bytes()).hexdigest()==manifest['source_sha256']
    report={'app_version':info['version'],'packaged_lookup_checks':len(definitions),'library_entries':911,
        'core_definitions_match':True,'original_cards_unchanged':len(original),'reviews_preserved':len(exported['reviews']),
        'source_file_unchanged':True,'automatic_collection_during_checks':False,
        'backup_before_import':str(backup)}
    (OUT/'packaged-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
