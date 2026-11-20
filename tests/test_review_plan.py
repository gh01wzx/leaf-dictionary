"""User-facing review contracts: continuation, truthful counts and due-time scheduling."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import unittest
from unittest.mock import patch

import helpers
import app
from fsrs import Card, State


class ReviewPlanTests(helpers.TempData, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.current = app.day_start(app.study_day(app.now())) + timedelta(hours=3)
        self.clock = patch('app.now', side_effect=lambda: self.current)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def grade(self, card_id, rating=3):
        row = helpers.full_row(card_id)
        return app.rate({'id':card_id, 'rating':rating, 'version':row['card_json'], 'include_next':True})

    def set_state(self, card_id, due, state=State.Review, paused=False):
        card = Card.from_json(helpers.full_row(card_id)['card_json'])
        card.state, card.step = state, None if state == State.Review else 0
        card.stability, card.difficulty = 8, 5
        card.last_review, card.due = self.current - timedelta(days=4), due
        with app.connect() as db:
            db.execute('UPDATE cards SET card_json=?,due=?,paused=? WHERE id=?',
                       (card.to_json(), due.isoformat(), int(paused), card_id))
        return card

    def test_goal_completion_never_blocks_continued_learning(self):
        app.update_settings({'daily_goal':1, 'daily_minimum':1, 'new_per_day':1})
        ids = [helpers.collect(w)['id'] for w in ('bank', 'field', 'exert', 'reluctant')]
        first = app.review_next()['card']
        result = self.grade(first['id'])
        self.assertTrue(result['stats']['goal']['met_goal'])
        self.assertIsNone(result['card'])
        self.assertEqual(result['stats']['queue']['continue_batch'], 3)
        result = app.add_new_today({'count':10, 'request_id':'continue-1', 'day':result['stats']['today']})
        self.assertEqual(result['queue']['new_left'], 3)
        self.assertEqual(result['queue']['extra_new'], 3, 'no phantom slots beyond available words')
        self.assertEqual(app.add_new_today({'count':10, 'request_id':'continue-1'})['queue']['extra_new'], 3)
        for _ in range(3):
            self.grade(app.review_next()['card']['id'])
        result = app.stats()
        self.assertEqual(result['goal']['done'], 4)
        self.assertEqual(result['queue']['new_total'], 0)
        self.assertEqual(result['queue']['continue_batch'], 0)
        self.assertEqual(result['queue']['later_today'], 4)
        self.assertEqual(result['goal']['new_today'], len(ids))
        self.assertEqual(result['goal']['old_today'], 0)

    def test_concurrent_retries_add_only_one_batch(self):
        app.update_settings({'new_per_day':0})
        for w in ('bank', 'field', 'exert', 'reluctant'):
            helpers.collect(w)
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda _: app.add_new_today({'count':2, 'request_id':'same-click'}), range(3)))
        self.assertEqual([r['queue']['extra_new'] for r in results], [2, 2, 2])
        app.add_new_today({'count':2, 'request_id':'another-click'})
        self.assertEqual(app.stats()['queue']['new_left'], 4)

    def test_day_rollover_rejects_old_top_up_and_resets_daily_counts(self):
        helpers.collect('bank')
        app.update_settings({'new_per_day':0})
        old_day = app.stats()['today']
        app.add_new_today({'count':1, 'request_id':'old', 'day':old_day})
        self.grade(app.review_next()['card']['id'])
        self.current = app.day_start(app.study_day(self.current) + timedelta(days=1))
        with self.assertRaises(app.ReviewConflict):
            app.add_new_today({'count':1, 'request_id':'late-click', 'day':old_day})
        stats = app.stats()
        self.assertEqual(stats['queue']['extra_new'], 0)
        self.assertEqual(stats['goal']['done'], 0)
        self.assertEqual(stats['queue']['review_ready'], 1)
        self.assertEqual(stats['streak'], 0)  # one word is below the default minimum

    def test_due_learning_then_due_reviews_then_new_words(self):
        old = helpers.collect('bank')['id']
        learning = helpers.collect('field')['id']
        new = helpers.collect('exert')['id']
        future = helpers.collect('reluctant')['id']
        self.set_state(old, self.current - timedelta(days=2))
        self.set_state(learning, self.current, State.Learning)
        self.set_state(future, self.current + timedelta(minutes=2), State.Relearning)
        self.assertEqual(app.review_next()['card']['id'], learning)
        result = self.grade(learning)
        self.assertEqual(result['card']['id'], old)
        result = self.grade(old)
        self.assertEqual(result['card']['id'], new)
        result = self.grade(new)
        self.assertIsNone(result['card'])
        self.assertIsNone(app.review_next(focus=future)['card'])
        self.current += timedelta(minutes=2)
        result = app.review_next()
        self.assertEqual(result['card']['id'], future)
        self.assertEqual(result['stats']['queue']['ready'], 1)

    def test_delayed_recall_excludes_immediate_repeats_cloze_and_future_records(self):
        first = helpers.collect('bank')['id']
        second = helpers.collect('exert')['id']
        prior = self.set_state(first, self.current).to_json()
        immediate = Card.from_json(prior)
        immediate.last_review = self.current - timedelta(hours=1)
        with app.connect() as db:
            rows = [
                (first, 1, self.current, prior, 'recognize'),
                (first, 3, self.current + timedelta(seconds=1), prior, 'recognize'),
                (second, 3, self.current, prior, 'cloze'),
                (second, 3, self.current, immediate.to_json(), 'recognize'),
                (second, 3, self.current + timedelta(days=1), prior, 'recognize'),
                (second, 3, self.current - timedelta(days=31), prior, 'recognize'),
            ]
            db.executemany('INSERT INTO reviews(card_id,rating,created,log_json,prev_card_json,mode) VALUES(?,?,?,\'{}\',?,?)',
                           [(cid, rating, at.isoformat(), version, mode) for cid, rating, at, version, mode in rows])
        self.current += timedelta(seconds=2)
        result = app.stats()['retention']
        self.assertEqual(result['reviews'], 1)
        self.assertEqual(result['rate'], 0, 'later successful repetition must not erase the delayed failure')

    def test_imported_established_word_is_not_counted_as_a_new_word(self):
        card_id = helpers.collect('bank')['id']
        self.set_state(card_id, self.current)
        result = self.grade(card_id)['stats']
        self.assertEqual(result['goal']['new_today'], 0)
        self.assertEqual(result['goal']['old_today'], 1)

    def test_forecast_excludes_new_and_paused_and_keeps_later_today_separate(self):
        ids = [helpers.collect(w)['id'] for w in ('bank', 'field', 'exert', 'reluctant', 'subtle')]
        tomorrow = app.day_start(app.study_day(self.current) + timedelta(days=1))
        self.set_state(ids[0], self.current + timedelta(minutes=10), State.Learning)
        self.set_state(ids[1], tomorrow)
        self.set_state(ids[2], tomorrow + timedelta(hours=1), paused=True)
        self.set_state(ids[3], tomorrow + timedelta(days=6))
        stats = app.stats()
        self.assertEqual(stats['queue']['later_today'], 1)
        self.assertEqual(sum(stats['forecast'].values()), 2)
        self.assertEqual(list(stats['forecast'].values()), [1, 0, 0, 0, 0, 0, 1])
        self.assertEqual(stats['queue']['new_total'], 1)
        self.assertEqual(stats['day_ends_at'], tomorrow.isoformat())

    def test_disabling_typing_really_disables_productive_cloze(self):
        card_id = helpers.collect('exert')['id']
        self.set_state(card_id, self.current)
        with app.connect() as db:
            db.execute("INSERT INTO reviews(card_id,rating,created,log_json) VALUES(?,3,?,'{}')",
                       (card_id, (self.current - timedelta(days=4)).isoformat()))
        self.assertEqual(app.review_next()['card']['mode'], 'cloze')
        app.update_settings({'typing':False})
        result = app.review_next()['card']
        self.assertEqual(result['mode'], 'recognize')
        self.assertIsNone(result['cloze'])

    def test_stale_undo_cannot_undo_a_reused_review_id(self):
        card = helpers.collect('bank')
        first = self.grade(card['id'])
        app.undo_review({'review_id':first['review_id'], 'card_id':card['id'], 'version':first['review_version']})
        self.current += timedelta(seconds=1)
        second = self.grade(card['id'], 1)
        self.assertEqual(first['review_id'], second['review_id'], 'SQLite may reuse the deleted latest row ID')
        with self.assertRaises(app.ReviewConflict):
            app.undo_review({'review_id':first['review_id'], 'card_id':card['id'], 'version':first['review_version']})
        self.assertEqual(app.stats()['review_attempts_today'], 1)
        app.undo_review({'review_id':second['review_id'], 'card_id':card['id'], 'version':second['review_version']})
        self.assertEqual(app.stats()['goal']['done'], 0)
        self.assertEqual(app.stats()['queue']['new_left'], 1)


if __name__ == '__main__':
    unittest.main()
