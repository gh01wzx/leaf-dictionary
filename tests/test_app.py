import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import helpers

class LearningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original = app.DATA_DIR
        app.DATA_DIR = Path(self.tmp.name)
        app.initialize()

    def tearDown(self):
        app.DATA_DIR = self.original
        self.tmp.cleanup()

    def save(self, word='reluctant', sense='0', **kw):
        return helpers.collect(word,**kw)

    def test_lexicon_and_curated_and_missing(self):
        self.assertGreater(app.MANIFEST['entries'], 700000)
        word = app.lookup(' RELUCTANT! ')
        self.assertTrue(word['found'])
        self.assertIn('不太愿意', word['insight']['summary'])
        self.assertFalse(app.lookup('zzzznotarealwordzz')['found'])
        self.assertEqual(app.stats()['total'], 0)
        self.assertTrue(app.lookup('put up with')['found'])

    def test_inflections(self):
        for form, base in [('went','go'),('children','child'),('running','run')]:
            with self.subTest(form=form):
                entry = app.lookup(form)
                self.assertTrue(entry['found'])
                self.assertEqual(entry['word'].lower(), base)

    def test_duplicate_queries_preserve_schedule_and_context(self):
        first = self.save(context='He was reluctant to leave.',source='A book')
        again = self.save(context='She was reluctant to agree.',source='Another book')
        self.assertEqual(first['id'], again['id'])
        self.assertEqual(first['card_json'], again['card_json'])
        self.assertEqual(again['lookups'], 2)
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM encounters').fetchone()[0], 2)

    def test_pending_replaced_without_losing_encounter(self):
        pending = self.save('bank','pending',context='We sat on the bank.',source='Chapter 2')
        selected = self.save('bank','1',context='We sat on the bank.',source='Chapter 2')
        self.assertEqual(pending['id'], selected['id'])
        self.assertEqual(app.stats()['total'], 1)
        self.assertIn('河岸', selected['meaning'])
        self.save('bank','0')
        self.assertEqual(app.stats()['total'], 1)
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM encounters').fetchone()[0], 1)

    def test_fsrs_updates_persist_and_reject_double_rating(self):
        card = self.save()
        self.assertEqual(app.stats()['due'], 1)
        next_card = app.review_next()['card']
        self.assertEqual(next_card['id'], card['id'])
        self.assertNotIn('preview', next_card)
        outcome = app.rate({'id':card['id'],'rating':3,'version':card['card_json']})
        self.assertEqual(outcome['stats']['reviewed_today'], 1)
        self.assertIsNone(app.review_next(last=card['id'])['card'])
        self.assertGreater(outcome['due'], app.now().isoformat())
        with self.assertRaises(ValueError):
            app.rate({'id':card['id'],'rating':3,'version':card['card_json']})
        app.initialize()
        self.assertEqual(app.stats()['total'], 1)
        self.assertEqual(app.stats()['reviewed_today'], 1)
        self.assertEqual(app.stats()['due'], 0)

    def test_paused_words_not_reviewed(self):
        card = self.save()
        with app.connect() as db:
            db.execute('UPDATE cards SET paused=1 WHERE id=?', (card['id'],))
        self.assertEqual(app.stats()['total'], 1)
        self.assertEqual(app.stats()['due'], 0)
        self.assertIsNone(app.review_next()['card'])
        self.assertEqual(len(app.library(status='paused')),1)

    def backup(self):
        payload = {'app':app.APP_ID,'version':1}
        with app.connect() as db:
            for table in ('cards','encounters','reviews'):
                payload[table] = [dict(r) for r in db.execute('SELECT * FROM ' + table)]
        return payload

    def test_backup_roundtrip_merges_and_preserves_reviews(self):
        card = self.save(context='He was reluctant to leave.')
        app.rate({'id':card['id'],'rating':1,'version':card['card_json']})
        payload = self.backup()
        self.assertEqual(app.import_backup(payload)['imported'],0)
        with tempfile.TemporaryDirectory() as other:
            app.DATA_DIR = Path(other)
            app.initialize()
            self.assertEqual(app.import_backup(payload)['imported'],1)
            self.assertEqual(app.stats()['reviewed_today'],1)
            self.assertEqual(app.library()[0]['context'],'He was reluctant to leave.')
            self.assertEqual(app.import_backup(payload)['imported'],0)
        app.DATA_DIR = Path(self.tmp.name)

    def test_bad_import_is_atomic(self):
        self.save()
        payload = self.backup()
        with app.connect() as db:
            db.execute('DELETE FROM cards')
        bad = dict(payload['cards'][0]); bad['word'] = 'broken'; bad['card_json'] = '{}'
        payload['cards'].append(bad)
        with self.assertRaises((KeyError,ValueError)):
            app.import_backup(payload)
        self.assertEqual(app.stats()['total'],0)

    def test_http_limits_csrf_and_full_flow(self):
        server = app.Server(('127.0.0.1',0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        def call(path, data=None, token=app.TOKEN, origin=None):
            headers = {'X-Leaf-Token':token, 'Content-Type':'application/json'}
            if origin: headers['Origin'] = origin
            req = urllib.request.Request(base + path, data=json.dumps(data).encode() if data is not None else None, headers=headers)
            with urllib.request.urlopen(req) as response:
                return json.load(response)
        try:
            self.assertEqual(call('/api/health')['app'],app.APP_ID)
            with urllib.request.urlopen(base) as response:
                html = response.read().decode()
                self.assertIn(app.TOKEN,html)
                self.assertIn(app.VERSION,html)
                self.assertIn("connect-src 'self'",response.headers['Content-Security-Policy'])
            for token,origin in [('wrong',None),(app.TOKEN,'https://example.com')]:
                with self.assertRaises(urllib.error.HTTPError) as cm:
                    call('/api/explain',{'query':'bank','save':True},token,origin)
                self.assertEqual(cm.exception.code,403)
            self.assertEqual(call('/api/stats')['total'],0)
            self.assertIn('bank',[item['word'] for item in call('/api/suggest?q=ban')['items']])
            saved = call('/api/explain',{'query':'bank','save':True})['saved_card']
            self.assertNotIn('explanation_json',saved)
            self.assertEqual(len(call('/api/export')['cards']),1)
            compact = call('/api/library')['cards']
            self.assertNotIn('card_json',compact[0])
            self.assertEqual(compact[0]['state'],'new')
            rated = call('/api/rate',{'id':saved['id'],'rating':3,'version':saved['card_json']})
            with self.assertRaises(urllib.error.HTTPError) as cm:
                call('/api/rate',{'id':saved['id'],'rating':3,'version':saved['card_json']})
            self.assertEqual(cm.exception.code,409)
            self.assertEqual(call('/api/stats')['review_attempts_today'],1)
            call('/api/undo',{'review_id':rated['review_id']})
            self.assertEqual(call('/api/stats')['review_attempts_today'],0)
            self.assertEqual(call('/api/settings',{'new_per_day':15})['new_per_day'],15)
            with self.assertRaises(urllib.error.HTTPError) as cm:
                call('/api/settings',{'retention':0.5})
            self.assertEqual(cm.exception.code,400)
            self.assertEqual(call('/api/delete',{'id':saved['id']})['stats']['total'],0)
            with self.assertRaises(urllib.error.HTTPError) as cm:
                call('/api/explain',{'query':'x' * 121})
            self.assertEqual(cm.exception.code,400)
            for removed in ('/api/lookup','/api/save','/api/model/restart'):
                with self.assertRaises(urllib.error.HTTPError) as cm:
                    call(removed,{'query':'bank'})
                self.assertEqual(cm.exception.code,404)
            with self.assertRaises(urllib.error.HTTPError) as cm:
                call('/app.py')
            self.assertEqual(cm.exception.code,404)
        finally:
            server.shutdown(); server.server_close(); thread.join()

if __name__ == '__main__':
    unittest.main()
