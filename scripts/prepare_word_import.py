"""Prepare an auditable import manifest without changing learning records."""
import collections
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path.home()/'Desktop'/'words.md'
OUT=ROOT/'reviews/words-import-2026-11-02'

def main():
    text=SOURCE.read_text(encoding='utf-8-sig')
    pattern=re.compile(r'•\s*([^•\n\r\[]+?)\s*\[([^\]\n]+)\]\s*[:：]\s*([^•\n\r]+)')
    matches=list(pattern.finditer(text))
    assert len(matches)==text.count('•'), 'Unparsed source bullet'
    # Independent extraction: inspect each bullet chunk, including inline entries.
    chunks=text.split('•')[1:]
    independent=[re.split(r'\s*\[',chunk.strip(),maxsplit=1)[0].strip() for chunk in chunks]
    assert independent==[m.group(1).strip() for m in matches]
    records=[]
    targets={}
    for i,m in enumerate(matches,1):
        head=m.group(1).strip()
        words=['sciatic','sciatica'] if head.lower()=='sciatic/sciatica' else [head.lower()]
        row={'record':i,'line':text.count('\n',0,m.start())+1,'headword':head,
            'words':words,'original_note':m.group(3).strip()}
        records.append(row)
        for word in words:targets.setdefault(word,[]).append(i)
    with sqlite3.connect((ROOT/'user_data/learning.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        existing=[dict(row) for row in db.execute('SELECT * FROM cards ORDER BY id')]
        prior_definitions=[dict(row) for row in db.execute('SELECT * FROM definition_overrides ORDER BY word')]
        OUT.mkdir(exist_ok=True)
        backup=ROOT/'user_data/backups'/('before-words-import-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.sqlite3')
        with sqlite3.connect(backup) as snapshot:db.backup(snapshot)
    all_words=list(targets)
    all_words.extend(row['word'] for row in existing if row['word'] not in targets)
    assert len(all_words)==len(set(all_words))
    manifest={'source':str(SOURCE),'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'source_records':records,'source_words':list(targets),'target_words':all_words,
        'source_mapping':targets,'existing_cards':existing,'existing_definitions':prior_definitions,
        'backup':str(backup),'counts':{'source_records':len(records),'unique_original_headwords':len(set(independent)),
        'source_words_after_split':len(targets),'existing_cards':len(existing),'target_cards':len(all_words)}}
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(manifest['counts']))
    for start in range(0,len(all_words),100):
        words=all_words[start:start+100]
        lines=[]
        for i,word in enumerate(words,start+1):
            notes=[records[n-1]['original_note'] for n in targets.get(word,[])]
            lines.append(f'{i}. {word} | '+(' / '.join(notes)[:100] if notes else '原生词本已有词'))
        (OUT/f'input-{start//100+1:02}.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Prepared manifest, source cross-check and backup; collection unchanged.')

if __name__=='__main__':main()
