"""Run the real executable against disposable local data; never touch the user's collection."""
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.request
import io
import wave

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:49186'

def main():
    with tempfile.TemporaryDirectory(prefix='leaf-packaged-') as temp:
        process = subprocess.Popen([str(ROOT / 'Leaf.exe'), '--no-browser', '--port', '49186', '--data-dir', temp])
        token = None
        def api(path, data=None):
            request = urllib.request.Request(BASE + '/api/' + path,
                data=json.dumps(data).encode() if data is not None else None,
                headers={'Content-Type':'application/json','X-Leaf-Token': token or ''})
            with urllib.request.urlopen(request, timeout=170) as response:
                return json.load(response)
        try:
            for _ in range(80):
                if process.poll() is not None:
                    raise RuntimeError('The packaged application exited before serving.')
                try:
                    assert api('health')['app'] == 'leaf-offline-dictionary-v1'
                    break
                except (OSError, AssertionError):
                    time.sleep(.25)
            else:
                raise RuntimeError('Application did not start in 20 seconds.')
            with urllib.request.urlopen(BASE) as response:
                html = response.read().decode()
            token = re.search(r'name="leaf-token" content="([^"]+)"',html)[1]
            info=api('info')
            assert info['version']=='1.1.0' and info['algorithm']=='FSRS-6'
            assert re.search(r'id="context-panel"[^>]*hidden', html)
            assert 'id="definition-dialog"' in html and 'id="card-sheet"' in html
            for asset, expected in (('requests.js','LatestRequest'),('speech.js','speakWord'),('study.js','checkAnswer'),('app.js','libraryPageSize'),('style.css','prefers-reduced-motion')):
                with urllib.request.urlopen(BASE+'/'+asset) as response:
                    assert expected in response.read().decode('utf-8-sig')
            assert info['entries'] > 700000
            assert any(item['word']=='reluctant' for item in api('suggest?q=relu')['items'])
            went=api('explain', {'query':'went'})
            assert 'go' in (went['lemma'], went['explanation'].get('related_lemma'))
            saved = api('explain', {'query':'bank','context':'We sat on the bank.','save':True})['saved_card']
            assert api('stats')['total'] == 1
            compact=api('library')['cards']
            assert len(compact)==1 and compact[0]['id']==saved['id']
            assert 'explanation_json' not in compact[0] and 'card_json' not in compact[0]
            page = api('library?limit=40')
            assert page['total'] == 1 and page['next_cursor'] is None
            assert page['cards'][0]['id'] == saved['id']
            detail = api('card?explain=1&id=' + str(saved['id']))
            assert detail['result']['query'] == 'bank' and detail['card']['id'] == saved['id']
            assert api('review')['card']['id'] == saved['id']
            result = api('rate', {'id':saved['id'],'rating':3,'version':saved['card_json']})
            assert result['stats']['reviewed_today'] == 1
            assert result['stats']['review_attempts_today'] == 1
            assert result['stats']['week'][result['stats']['today']] == 1
            assert len(api('export')['reviews']) == 1
            generated=api('explain',{'query':'informed','context':'Her choices are informed by years of experience.','save':True})
            assert generated['source_kind']=='dictionary' and 'model' not in generated
            assert generated['found'] and generated['word']=='informed'
            assert any(word in generated['explanation']['context_meaning'] for word in ('影响','塑造','依据','形成','基于','指导','指引'))
            assert generated['saved_card']['id']
            api('settings', {'daily_goal':1, 'daily_minimum':1, 'new_per_day':1})
            completed = api('review')
            assert completed['stats']['goal']['met_goal'] and completed['card'] is None
            assert completed['stats']['queue']['continue_batch'] == 1
            top_up = {'count':10, 'request_id':'packaged-continue', 'day':completed['stats']['today']}
            assert api('extra-new', top_up)['queue']['new_left'] == 1
            assert api('extra-new', top_up)['queue']['extra_new'] == 1
            assert api('review')['card']['id'] == generated['saved_card']['id']
            api('settings', {'new_per_day':10})
            cached=api('explain',{'query':'informed','context':'Her choices are informed by years of experience.','save':False})
            assert cached['explanation']==generated['explanation']
            field=api('explain',{'query':'field','save':False})
            assert '领域' in field['explanation']['core_meaning']
            assert '电场' not in field['explanation']['core_meaning']
            assert any('电场' in str(text) for text in field['explanation']['supplementary_senses'])
            total=api('stats')['total']
            demagogic=api('explain',{'query':'demagogic'})
            assert api('stats')['total']==total
            assert '争取支持' in demagogic['explanation']['core_meaning']
            assert 'demagogue' not in demagogic['explanation']['core_meaning']
            assert '自行车' in api('explain',{'query':'bicycle'})['explanation']['core_meaning']
            added=api('explain',{'query':'demagogic','context':'First context.','save':True})['saved_card']
            api('rate',{'id':added['id'],'rating':3,'version':added['card_json']})
            prior=api('card?id='+str(added['id']))['card']
            again=api('explain',{'query':'DEMAGOGIC','context':'Second context.','save':True})['saved_card']
            assert again['id']==added['id'] and again['card_json']==prior['card_json'] and again['due']==prior['due']
            assert api('stats')['total']==total+1
            assert len(api('card?id='+str(added['id']))['encounters'])==2
            assert api('info')['dictionary']['learner']['entries']>84000
            assert any('领域' in x['gloss'] for x in field['explanation']['learner_senses'])
            unless=api('explain',{'query':'unless'})
            assert '除非' in unless['explanation']['core_meaning']
            running=api('explain',{'query':'run'})['explanation']
            assert '不能在这个意义下' not in str(running)
            assert len(api('export')['cards'])==total+1
            assert 'id="auto-save"' not in html
            original=api('explain',{'query':'canonical'})['explanation']['core_meaning']
            total_before_edit=api('stats')['total']
            custom=api('definition',{'word':' CANONICAL! ','meaning':'这是我自己理解的、公认的规范。','expected':''})
            assert api('stats')['total']==total_before_edit
            changed=api('explain',{'query':'canonical'})
            assert changed['explanation']['custom_definition']
            assert changed['explanation']['core_meaning']==custom['meaning']
            assert changed['explanation']['dictionary_core_meaning']==original
            card=api('explain',{'query':'canonical','save':True})['saved_card']
            assert card['meaning']==custom['meaning']
            assert any(c['word']=='canonical' and c['meaning']==custom['meaning'] for c in api('library?compact=1')['cards'])
            assert len(api('export')['definition_overrides'])==1
            api('definition',{'word':'canonical','meaning':None,'expected':custom['updated']})
            assert api('explain',{'query':'canonical'})['explanation']['core_meaning']==original
            assert api('card?id='+str(card['id']))['card']['card_json']==card['card_json']
            phrase=dict(api('card?id='+str(card['id']))['card'])
            state=json.loads(phrase['card_json']);state['card_id']+=100000
            phrase.update(id=9876,word='with bearing of',sense_key='personal:import',meaning='带着某种仪态或风度。',
                explanation_json='',card_json=json.dumps(state),source='words.md')
            api('import',{'app':'leaf-offline-dictionary-v1','version':1,'cards':[phrase]})
            imported=api('explain',{'query':'with bearing of'})
            assert imported['found'] and imported['can_save']
            assert imported['dictionary_source']=='我的整理词条'
            assert imported['explanation']['core_meaning']==phrase['meaning']
            assert not imported['explanation']['warning']
            speech=api('speech')
            assert speech['available'] and speech['offline']
            before_speech=api('stats')['total']
            request=urllib.request.Request(BASE+'/api/speech',data=json.dumps({'word':'demagogic','accent':speech['default']}).encode(),headers={'Content-Type':'application/json','X-Leaf-Token':token})
            with urllib.request.urlopen(request,timeout=30) as response:
                assert response.headers['Content-Type']=='audio/wav'
                with wave.open(io.BytesIO(response.read()),'rb') as audio:
                    assert audio.getnframes()>1000
            assert api('stats')['total']==before_speech
            print('Packaged executable: lookup, suggestions, personal definitions, export, learner dictionary, offline audio, collection, and FSRS PASS')
        finally:
            if token:
                try:
                    api('quit', {})
                except OSError:
                    pass
            try:
                process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)

if __name__ == '__main__':
    main()
