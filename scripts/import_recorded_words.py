"""Merge the reviewed word list atomically, then independently verify every row.

Default mode rehearses against a separate copy. --apply targets the user's data.
No remote service or model is used to author or import these fixed definitions.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import app

OUT=ROOT/'reviews/words-import-2026-11-02'
SOURCE=Path.home()/'Desktop'/'words.md'

def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def definitions():
    items={}
    for path in sorted(OUT.glob('definitions-*.psv')):
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line.strip():continue
            word,meaning=line.split('|',1)
            assert word==app.normalize(word) and word not in items,(path,word)
            assert 12<=len(meaning)<=3000 and re.search(r'[\u3400-\u9fff]',meaning),word
            items[word]=meaning
    return items

def snapshot():
    with app.connect() as db:
        return {table:[dict(row) for row in db.execute('SELECT * FROM '+table+' ORDER BY '+('word' if table=='definition_overrides' else 'id'))]
            for table in ('cards','reviews','encounters','definition_overrides')}

def prepare_new_entry(word,meaning):
    entry=app.lookup(word)
    learned=app.learner_entry(word,entry.get('word',''))
    result=app.make_result(word,'','words.md',entry,app.CURATED.get(entry.get('word','').lower()),entry.get('definition',''),learned)
    rich=result['explanation']
    if not result.get('can_save'):
        rich.update(valid_word=True,origin='personal',lemma=word,core_meaning=meaning,
            core_label='核心释义',warning='',source_note='由旧生词笔记导入，核心释义已重新整理。',
            dictionary_source='我的整理词条',reference_url='',reference_title='')
        result['sense_key']='personal:'+hashlib.sha256(word.encode()).hexdigest()[:24]
    return result['sense_key'],json.dumps(app.stored_explanation(rich),ensure_ascii=False),rich

def merge(items,before):
    existing={row['word']:row for row in before['cards']}
    assert set(existing)<=set(items), 'New words were added after preparation; write their definitions first.'
    prepared={word:prepare_new_entry(word,meaning) for word,meaning in items.items() if word not in existing}
    original_ids={app.Card.from_json(row['card_json']).card_id for row in before['cards']}
    current=app.now();stamp=current.isoformat()
    next_id=max({int(current.timestamp()*1000),*(value+1 for value in original_ids)})
    new_ids=[]
    with app.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        for word,(sense,rich_json,rich) in prepared.items():
            card=app.Card(card_id=next_id,due=current);next_id+=1
            card_id=db.execute('''INSERT INTO cards(word,sense_key,meaning,context,source,card_json,due,created,updated,explanation_json)
                VALUES(?,?,?,?,?,?,?,?,?,?)''',(word,sense,rich['core_meaning'],'','words.md',card.to_json(),stamp,stamp,stamp,rich_json)).lastrowid
            new_ids.append(card_id)
        for word,meaning in items.items():
            db.execute('INSERT INTO definition_overrides(word,meaning,updated) VALUES(?,?,?) '
                'ON CONFLICT(word) DO UPDATE SET meaning=excluded.meaning,updated=excluded.updated',(word,meaning,stamp))
    return new_ids

def verify(items,before,new_ids):
    after=snapshot()
    actual={row['word']:row for row in after['cards']}
    assert set(actual)==set(items), 'The final collection does not match the complete target list.'
    by_id={row['id']:row for row in after['cards']}
    for old in before['cards']:assert by_id[old['id']]==old,('Existing card changed',old['word'])
    for table in ('reviews','encounters'):assert before[table]==after[table],table
    overrides={row['word']:row for row in after['definition_overrides']}
    checks=[]
    for word,meaning in items.items():
        assert overrides[word]['meaning']==meaning,word
        shown=app.dictionary_explain({'query':word})
        assert shown['found'] and shown['can_save'] and shown['explanation']['core_meaning']==meaning,word
        assert not shown['explanation'].get('warning'),word
        assert shown['saved_card']['id']==actual[word]['id'],word
        card=dict(actual[word]);card['explanation']=json.loads(card['explanation_json']) if card['explanation_json'] else None
        if card['explanation'] and card['explanation'].get('learner_word'):
            card['explanation']=shown['explanation']
        card=app.card_definition(card,overrides[word])
        assert card['definition']['core_meaning']==meaning and card['meaning']==meaning,word
        checks.append({'word':word,'lookup':True,'review_definition':True,'collected':True,
            'meaning_sha256':hashlib.sha256(meaning.encode()).hexdigest()})
    assert len(app.library(brief=True))==len(items)
    assert {row['word']:row['meaning'] for row in app.library(brief=True)}==items
    internal_ids=[app.Card.from_json(row['card_json']).card_id for row in after['cards']]
    assert len(internal_ids)==len(set(internal_ids)), 'FSRS card ids collide.'
    for card_id in new_ids:
        card=app.Card.from_json(by_id[card_id]['card_json'])
        assert card.last_review is None and card.stability is None and card.difficulty is None
    # Reparse the original document independently, rather than trusting the manifest.
    text=SOURCE.read_text(encoding='utf-8-sig')
    heads=[re.split(r'\s*\[',chunk.strip(),maxsplit=1)[0].strip().lower() for chunk in text.split('•')[1:]]
    source_words=set()
    for head in heads:source_words.update(['sciatic','sciatica'] if head=='sciatic/sciatica' else [head])
    assert source_words<=set(actual), sorted(source_words-set(actual))
    with app.connect() as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        assert not db.execute('SELECT lower(trim(word)),COUNT(*) FROM cards GROUP BY lower(trim(word)) HAVING COUNT(*)>1').fetchall()
    return {'source_records_checked':len(heads),'source_unique_original_headwords':len(set(heads)),
        'source_words_after_split':len(source_words),'source_records_missing':0,
        'existing_cards_preserved':len(before['cards']),'added_cards':len(new_ids),'final_cards':len(actual),
        'rewritten_core_definitions':len(items),'missing_definitions':0,'duplicate_cards':0,
        'existing_review_records_preserved':len(before['reviews']),'existing_encounters_preserved':len(before['encounters']),
        'lookup_checks_passed':len(checks),'review_definition_checks_passed':len(checks),
        'sqlite_integrity':'ok','checks':checks}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==manifest['source_sha256'],'Source changed since parsing.'
    items=definitions()
    assert set(items)==set(manifest['target_words']) and len(items)==911
    dump(OUT/'definitions.json',items)
    (OUT/'全部核心释义.md').write_text('# 生词本全部核心释义\n\n2026-11-02 逐词整理，共 '+str(len(items))+' 条。\n\n'+
        '\n\n'.join('## '+word+'\n\n'+meaning for word,meaning in items.items())+'\n',encoding='utf-8')
    if not args.apply:
        rehearsal=OUT/'rehearsal';rehearsal.mkdir(exist_ok=True)
        with sqlite3.connect((ROOT/'user_data/learning.sqlite3').as_uri()+'?mode=ro',uri=True) as reader,sqlite3.connect(rehearsal/'learning.sqlite3') as writer:
            reader.backup(writer)
        app.DATA_DIR=rehearsal
    else:
        app.backup_learning_database('before-reviewed-words-import')
    before=snapshot()
    new_ids=merge(items,before)
    report=verify(items,before,new_ids)
    report.update(mode='applied' if args.apply else 'rehearsal',verified_utc=app.now().isoformat(),
        source_sha256=manifest['source_sha256'])
    dump(OUT/('final-verification.json' if args.apply else 'rehearsal-verification.json'),report)
    if args.apply:
        with app.connect() as db:
            backup={'app':app.APP_ID,'version':1,'exported':app.now().isoformat()}
            for table in ('cards','encounters','reviews','definition_overrides'):
                backup[table]=[dict(row) for row in db.execute('SELECT * FROM '+table)]
        dump(OUT/'after-import-backup.json',backup)
    print(json.dumps({k:v for k,v in report.items() if k!='checks'},ensure_ascii=False))

if __name__=='__main__':main()
