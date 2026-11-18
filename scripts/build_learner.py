"""Audit every source sense and build an offline, attributed derivative database.

Semantic edits are explicit, source-addressed patches, not heuristic rewrites.
Rule flags are review candidates, never reported as proven translation errors.
"""
from collections import Counter
import copy
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dictionary_engine import READABLE_ENTRIES
from learner_corrections import (ADDITIONS, ALIASES, OVERVIEWS, SENSE_PATCHES,
    FIELD_ADDITIONS, REFERENCES, LICENSE_NOTICE, sense, FUNCTION_WORDS, FUNCTION_OVERVIEWS, function_sense)

INPUT = ROOT/'downloads/open-dictionary-v2/distribution.jsonl.gz'
EXPECTED_ARCHIVE = '69af69cdc685b5dce465613d1cc8fffb598eb46714f57cf73bd6606c2ceb7e43'
EXPECTED_CONTENT = '95026a4b78aa83f1f32481e8ff30ea3f7d942b648b3d6e66ef64ca3a194cb66e'
LEGACY = {'obsolete','archaic','dated','rare'}
SPECIALIST = {'physics','chemistry','computing','programming','mathematics','heraldry',
    'medicine','anatomy','zoology','botany','astrology','astronomy','television','electronics'}
RULE_CANDIDATE = re.compile(r'不能.*(?:但|可以|可说|例如)')

def pack(value):
    return zlib.compress(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode(),6)

def classify(m):
    if m['proper']:
        return 'proper'
    if set(m['labels']) & LEGACY or m['priority']=='rare':
        return 'rare'
    if m['priority']!='core' and set(m['topics']) & SPECIALIST:
        return 'specialist'
    return 'main'

def compile_entry(raw, counts, events, flags):
    word=raw['normalized_headword']
    doc={'word':word,'headword':raw['headword'],'senses':[],'phonetics':[],
        'overview':OVERVIEWS.get(word,''),'references':REFERENCES.get(word,[]),
        'entry_id':raw['entry_id'],'corrected':False,'forms':[]}
    if raw.get('schema_version')!='distribution_entry_v5' or raw.get('definition_language',{}).get('code')!='zh-Hans':
        raise ValueError(f'Unexpected schema/language: {word}')
    keys=set(); seen={}
    for group in raw['pos_groups']:
        pos,etymology=group['pos'],group['etymology_id']
        for pronunciation in group.get('pronunciations',[]):
            ipa=pronunciation.get('ipa')
            if ipa and ipa not in doc['phonetics']:doc['phonetics'].append(ipa)
        for form in group.get('forms',[]):
            if form.get('text') and any(t in {'plural','past','participle','present','third-person','singular','comparative','superlative'} for t in form.get('tags',[])):
                doc['forms'].append(form['text'].lower())
        for source in group['meanings']:
            counts['source_senses']+=1
            sid=source['sense_id'];key=(pos,etymology,sid)
            if key in keys:raise ValueError(f'Duplicate source sense identity: {word}/{key}')
            keys.add(key)
            definition=source.get('learner_explanation') or ''
            if source.get('priority') not in ('core','common','rare'):
                raise ValueError(f'Invalid priority: {word}/{key}')
            if not definition.strip() or not re.search(r'[\u3400-\u9fff]',definition):
                flags.append(dict(word=word,key=key,issue='unusable_chinese_definition',original=source))
                counts['quarantined_senses']+=1
                continue
            for field in ('learner_explanation','short_gloss','usage_note'):
                value=source.get(field)
                if value is not None and (not isinstance(value,str) or '\ufffd' in value):
                    raise ValueError(f'Invalid text: {word}/{key}/{field}')
            for example in source.get('examples',[]):
                if not isinstance(example.get('text'),str) or not isinstance(example.get('translation'),str):
                    raise ValueError(f'Invalid example: {word}/{key}')
            if not source.get('examples') and source['priority']!='rare':
                counts['source_main_senses_without_examples']+=1
            original_usage=source.get('usage_note') or ''
            if RULE_CANDIDATE.search(original_usage):
                flags.append(dict(word=word,key=key,issue='possible_rule_contradiction',original=original_usage))
                counts['rule_review_candidates']+=1
            m=dict(pos=pos,etymology=etymology,sid=sid,gloss=source.get('short_gloss') or '',
                definition=definition,priority=source['priority'],labels=source.get('labels',[]),
                topics=source.get('topics',[]),proper=bool(group.get('proper_name')),
                examples=source.get('examples',[]),usage='',verified_usage=False)
            # Every source rule remains available in the immutable source archive;
            # only positively reviewed rules are shipped as usage advice.
            if original_usage:counts['unreviewed_usage_notes_not_published']+=1
            if set(m['labels']) & LEGACY and m['priority']!='rare':
                events.append(dict(word=word,key=key,change='legacy_priority',before=m['priority'],after='rare',basis=m['labels']))
                m['priority']='rare';counts['legacy_priority_repairs']+=1
            patch=SENSE_PATCHES.get((word,*key))
            if patch:
                events.append(dict(word=word,key=key,change='reviewed_sense_patch',before=copy.deepcopy(source),after=patch,references=REFERENCES[word]))
                m.update(patch);doc['corrected']=True;counts['reviewed_sense_patches']+=1
            if word=='act' and pos=='noun' and etymology=='et1':
                m['proper']=True
                events.append(dict(word=word,key=key,change='exam_name_separated_from_ordinary_word'))
            m['section']=classify(m)
            # Merge only exact duplicates within the same part of speech. Distinct
            # meanings and examples stay distinct even when short glosses match.
            identity=(pos,re.sub(r'\s+','',m['definition']),m['gloss'])
            if identity in seen:
                prior=seen[identity]
                for example in m['examples']:
                    if example not in prior['examples']:prior['examples'].append(example)
                events.append(dict(word=word,key=key,change='exact_duplicate_merged',kept=prior['sid']))
                counts['exact_duplicate_senses_merged']+=1
                continue
            seen[identity]=m;doc['senses'].append(m)
    if word=='field':
        for new in FIELD_ADDITIONS:
            new=copy.deepcopy(new);new.update(etymology='editorial',section='main')
            doc['senses'].append(new)
            events.append(dict(word=word,change='missing_sense_added',after=new,references=REFERENCES[word]))
            counts['reviewed_senses_added']+=1
        doc['corrected']=True
        doc['primary_keys']=[['noun','editorial','editorial-domain'],['noun','et1','s1'],['verb','et1','s4']]
    if word in FUNCTION_WORDS:
        new=function_sense(word);doc['senses'].insert(0,new)
        doc['overview']=FUNCTION_OVERVIEWS.get(word,f"{word} 作连词时，{new['definition']}")
        doc['primary_keys']=[['conj','editorial','editorial-conjunction']]
        doc['references']=list(dict.fromkeys(doc['references']+['https://www.collinsdictionary.com/dictionary/english/'+word]))
        doc['corrected']=True
        events.append(dict(word=word,change='missing_conjunction_pos_added',after=new,references=doc['references']))
        counts['conjunction_senses_restored']+=1
    if doc['overview']:
        counts['reviewed_overviews']+=1;doc['corrected']=True
        events.append(dict(word=word,change='reviewed_overview',before=raw['headword_summary'],after=doc['overview'],references=doc['references']))
    # No unreviewed headword summary or memory hook is substituted for a definition.
    if not doc['senses']:raise ValueError(f'No usable senses: {word}')
    doc['senses'].sort(key=lambda m:({'main':0,'specialist':1,'rare':2,'proper':3}[m['section']],{'core':0,'common':1,'rare':2}[m['priority']]))
    return doc

def build():
    if hashlib.sha256(INPUT.read_bytes()).hexdigest()!=EXPECTED_ARCHIVE:
        raise ValueError('Source archive checksum mismatch')
    counts=Counter();events=[];flags=[];content_hash=hashlib.sha256()
    target=ROOT/'data/learner.sqlite3'
    stage=target.with_suffix('.staging.sqlite3')
    # Rebuild only our explicitly named staging artifact, never user learning data.
    if stage.exists():stage.unlink()
    db=sqlite3.connect(stage)
    db.executescript('''CREATE TABLE entries(word TEXT PRIMARY KEY,document BLOB NOT NULL);
        CREATE TABLE forms(form TEXT NOT NULL,word TEXT NOT NULL,PRIMARY KEY(form,word));
        CREATE TABLE aliases(alias TEXT PRIMARY KEY,word TEXT NOT NULL);
        CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);''')
    heads=set();form_words=set()
    with gzip.open(INPUT,'rb') as stream:
        for line in stream:
            content_hash.update(line);raw=json.loads(line)
            doc=compile_entry(raw,counts,events,flags);word=doc['word']
            db.execute('INSERT INTO entries VALUES(?,?)',(word,pack(doc)))
            heads.add(word);counts['source_entries']+=1
            for form in doc.pop('forms'):
                if form!=word:
                    db.execute('INSERT OR IGNORE INTO forms VALUES(?,?)',(form,word));form_words.add(form)
    if content_hash.hexdigest()!=EXPECTED_CONTENT:raise ValueError('Source content checksum mismatch')
    # Previously reviewed demo entries become real fallback data, rather than
    # pretending that missing source entries were present in the release.
    additions=copy.deepcopy(ADDITIONS)
    for word in FUNCTION_WORDS:
        if word not in heads:
            m=function_sense(word)
            additions[word]={'overview':f"{word} 作连词时，{m['definition']}",'senses':[m],
                'references':['https://www.collinsdictionary.com/dictionary/english/'+word]}
            counts['conjunction_senses_restored']+=1
    for word in ('demagogic','demagogical','demagogue','demagogy','demagoguery'):
        old=READABLE_ENTRIES[word]
        additions[word]={'overview':old['core_meaning'],'senses':[sense(
            'adj' if word in ('demagogic','demagogical') else 'noun',
            '煽动民众情绪争取支持的' if word in ('demagogic','demagogical') else '煽动民众的政客' if word=='demagogue' else '煽动民众的做法',
            old['core_meaning'],old.get('example_en',''),old.get('example_zh',''))],
            'references':[old['reference_url']],'word_family':old.get('word_family',''),
            'reviewed_segments':True}
        additions[word]['senses'][0]['labels']=['disapproving']
    for word,data in additions.items():
        if word in heads:raise ValueError(f'Addition would replace original entry: {word}')
        doc={'word':word,'headword':word,'phonetics':[],'entry_id':'leaf:'+word,
            'overview':data['overview'],'senses':data['senses'],'references':data['references'],
            'corrected':True,'word_family':data.get('word_family','')}
        for i,m in enumerate(doc['senses']):m.update(sid='editorial-'+str(i),section='main',etymology='editorial')
        db.execute('INSERT INTO entries VALUES(?,?)',(word,pack(doc)));heads.add(word)
        events.append(dict(word=word,change='reviewed_entry_added',after=doc,references=data['references']))
        counts['reviewed_entries_added']+=1
        for form in data.get('forms',[]):
            db.execute('INSERT OR IGNORE INTO forms VALUES(?,?)',(form,word));form_words.add(form)
    for alias,word in ALIASES.items():
        if word not in heads:raise ValueError(f'Missing spelling target: {alias}->{word}')
        if alias not in heads:
            db.execute('INSERT INTO aliases VALUES(?,?)',(alias,word));counts['spelling_aliases_added']+=1
            events.append(dict(word=alias,change='spelling_alias_added',after=word))
    # Recover only source-attested inflections, never fuzzy stemming or arbitrary
    # mappings to a different part of speech (inform != informed adjective).
    with sqlite3.connect(ROOT/'data/dictionary.sqlite3') as base:
        for form,word in base.execute('SELECT form,word FROM forms'):
            if word.lower() in heads and form.lower() not in heads:
                db.execute('INSERT OR IGNORE INTO forms VALUES(?,?)',(form.lower(),word.lower()))
                form_words.add(form.lower())
        missing=[dict(word=w,rank=rank,translation=translation) for w,rank,translation in base.execute(
            'SELECT word,rank,translation FROM words ORDER BY rank,word LIMIT 10000')
            if w.lower() not in heads and w.lower() not in form_words and w.lower() not in ALIASES]
    counts['compiled_entries']=len(heads)
    counts['missing_in_base_top10000_after_repairs']=len(missing)
    counts['form_records']=db.execute('SELECT COUNT(*) FROM forms').fetchone()[0]
    report={'edition':'Leaf corrected learner data 1','scope':'Every source entry and sense structurally scanned; semantic review is limited to explicit patches.',
        'source_archive_sha256':EXPECTED_ARCHIVE,'source_content_sha256':EXPECTED_CONTENT,
        'counts':dict(counts),'remaining_common_coverage_gaps':missing,
        'limitations':['No whole-corpus semantic accuracy claim.','Generated usage rules withheld unless reviewed.','Missing/unsupported learner entries fall back to ECDICT Chinese, visibly labelled.']}
    for key,value in {'edition':report['edition'],'source_url':'https://github.com/ahpxex/open-dictionary/releases/tag/v2.0',
        'license':'CC BY-SA 4.0','counts':dict(counts),'source_sha256':EXPECTED_CONTENT}.items():
        db.execute('INSERT INTO metadata VALUES(?,?)',(key,json.dumps(value,ensure_ascii=False)))
    db.commit()
    if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Built database failed integrity check')
    db.close();stage.replace(target)
    (ROOT/'reviews/learner-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    for name,records in [('learner-changes.jsonl',events),('learner-review-queue.jsonl',flags)]:
        with (ROOT/'reviews'/name).open('w',encoding='utf-8') as out:
            for record in records:out.write(json.dumps(record,ensure_ascii=False)+'\n')
    (ROOT/'licenses/Open-Dictionary-CC-BY-SA-4.0.txt').write_text(LICENSE_NOTICE,encoding='utf-8')
    print(json.dumps(dict(counts)),flush=True)
    print('Compiled size MiB:',round(target.stat().st_size/1048576,1),flush=True)

if __name__=='__main__':build()
