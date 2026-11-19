"""Review science: daily new-word cap, interleaving, receptive -> productive, undo, own sentences."""
from datetime import timedelta
from unittest.mock import patch
import unittest

from fsrs import Card, Rating, State

import app
import helpers


class StudyTests(helpers.TempData, unittest.TestCase):
    def mature(self, card_id, reviews=1, stability=10.0):
        """Turn a card into an established review card that is due now."""
        current = app.now()
        with app.connect() as db:
            card = Card.from_json(db.execute('SELECT card_json FROM cards WHERE id=?', (card_id,)).fetchone()[0])
            card.state, card.step, card.stability, card.difficulty = State.Review, None, stability, 5.0
            card.last_review, card.due = current - timedelta(days=12), current - timedelta(hours=1)
            db.execute('UPDATE cards SET card_json=?,due=? WHERE id=?', (card.to_json(), card.due.isoformat(), card_id))
            for i in range(reviews):
                db.execute('INSERT INTO reviews(card_id,rating,created,log_json) VALUES(?,?,?,?)',
                    (card_id, 3, (current - timedelta(days=20 - i)).isoformat(), '{}'))

    def test_new_words_are_capped_per_day_but_reviews_are_not(self):
        app.update_settings({'new_per_day':2})
        ids = [helpers.collect(w)['id'] for w in ('bank', 'field', 'subtle', 'reluctant')]
        self.assertEqual(app.stats()['due'], 2)
        seen = set()
        for _ in range(2):
            card = app.review_next()['card']
            seen.add(card['id'])
            self.assertTrue(card['progress']['is_new'])
            app.rate({'id':card['id'], 'rating':3, 'version':card['card_json']})
        queue = app.stats()['queue']
        self.assertEqual(queue['new_left'], 0)
        self.assertEqual(queue['new_today'], 2)
        self.assertEqual(queue['new_total'], 2)
        unseen = next(i for i in ids if i not in seen)
        self.mature(unseen, reviews=2)
        self.assertGreaterEqual(app.stats()['queue']['review_due'], 1)

    def test_newest_words_are_introduced_first(self):
        helpers.collect('bank')
        newest = helpers.collect('field')
        self.assertEqual(app.review_next()['card']['id'], newest['id'])

    def test_new_words_interleave_with_reviews(self):
        old = [helpers.collect(w)['id'] for w in ('bank', 'subtle', 'reluctant', 'field')]
        for card_id in old:
            self.mature(card_id, reviews=2)
        new = helpers.collect('ubiquitous')['id']
        order = []
        for _ in range(5):
            card = app.review_next()['card']
            order.append(card['id'])
            app.rate({'id':card['id'], 'rating':3, 'version':card['card_json']})
        self.assertIn(new, order)
        self.assertNotEqual(order[0], new)

    def test_established_words_alternate_with_productive_cloze(self):
        card_id = helpers.collect('exert')['id']
        self.mature(card_id, reviews=1)
        card = app.review_next()['card']
        self.assertEqual(card['mode'], 'cloze')
        cloze = card['cloze']
        self.assertTrue(any(s['blank'] for s in cloze['segments']))
        self.assertIn('exert', cloze['accept'])
        self.assertIn('exerts', cloze['accept'])
        self.assertTrue(cloze['hint'])
        sentence = ''.join(s['text'] for s in cloze['segments'] if not s['blank'])
        self.assertNotRegex(sentence.lower(), r'\bexert')
        app.rate({'id':card_id, 'rating':3, 'version':card['card_json'], 'mode':'cloze'})
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT mode FROM reviews ORDER BY id DESC').fetchone()[0], 'cloze')

    def test_new_and_learning_words_use_recognition(self):
        helpers.collect('exert')
        self.assertEqual(app.review_next()['card']['mode'], 'recognize')

    def test_own_sentence_becomes_a_cloze_context(self):
        card_id = helpers.collect('exert')['id']
        result = app.add_sentence({'id':card_id, 'text':'Parents exert a quiet influence on their children.'})
        self.assertTrue(result['contains_word'])
        self.assertFalse(app.add_sentence({'id':card_id, 'text':'This sentence lacks the word.'})['contains_word'])
        self.mature(card_id, reviews=1)
        cloze = app.review_next()['card']['cloze']
        self.assertTrue(cloze['own'])
        self.assertEqual(cloze['answer'], 'exert')
        with self.assertRaises(ValueError):
            app.add_sentence({'id':card_id, 'text':'中文'})

    def test_cloze_extracts_one_sentence_from_a_long_passage(self):
        passage = 'He had worked all day. Then he exerted himself once more to lift the box. Afterwards he rested.'
        cloze = app.build_cloze('exert', app.word_forms('exert'), [{'text':passage}], 0)
        text = ''.join(s['text'] for s in cloze['segments'])
        self.assertEqual(text, 'Then he exerted himself once more to lift the box.')
        self.assertEqual(cloze['answer'], 'exerted')

    def test_word_forms_exclude_exchange_codes(self):
        forms = app.word_forms('informed')
        self.assertIn('informed', forms)
        self.assertTrue(all(len(f) > 2 for f in forms))

    def test_undo_restores_schedule_and_only_the_latest_rating(self):
        helpers.collect('bank')
        helpers.collect('field')
        first = app.review_next()['card']
        r1 = app.rate({'id':first['id'], 'rating':3, 'version':first['card_json']})
        second = app.review_next(last=first['id'])['card']
        self.assertNotEqual(second['id'], first['id'])
        r2 = app.rate({'id':second['id'], 'rating':1, 'version':second['card_json']})
        with self.assertRaises(app.ReviewConflict):
            app.undo_review({'review_id':r1['review_id']})
        app.undo_review({'review_id':r2['review_id']})
        restored = helpers.full_row(second['id'])
        self.assertEqual(restored['card_json'], second['card_json'])
        self.assertEqual(restored['due'], second['due'])
        self.assertEqual(app.review_next(focus=second['id'])['card']['id'], second['id'])
        self.assertEqual(app.stats()['review_attempts_today'], 1)

    def test_retention_setting_changes_future_intervals(self):
        card_id = helpers.collect('bank')['id']
        self.mature(card_id, reviews=2, stability=20.0)
        row = helpers.full_row(card_id)
        intervals = {}
        for retention in (0.85, 0.95):
            card = Card.from_json(row['card_json'])
            reviewed = app.now()
            updated, _ = Scheduler_no_fuzz(retention).review_card(card, Rating.Good, review_datetime=reviewed)
            intervals[retention] = updated.due - reviewed
        self.assertGreater(intervals[0.85], intervals[0.95])

    def test_settings_are_validated(self):
        for bad in ({'new_per_day':-1}, {'new_per_day':101}, {'new_per_day':True}, {'retention':0.5}, {'typing':'yes'}):
            with self.assertRaises(ValueError):
                app.update_settings(bad)
        self.assertEqual(app.get_settings(), app.DEFAULT_SETTINGS)

    def test_library_filters_states_and_escapes_search(self):
        a = helpers.collect('bank')['id']
        b = helpers.collect('field')['id']
        self.mature(a, reviews=3, stability=30.0)
        self.assertEqual([r['id'] for r in app.library(status='mastered')], [a])
        self.assertEqual([r['id'] for r in app.library(status='new')], [b])
        self.assertEqual(app.library(q='%'), [])
        self.assertEqual(app.library(q='_'), [])
        row = next(r for r in app.library(brief=True) if r['id'] == a)
        self.assertEqual(row['state'], 'review')
        self.assertNotIn('card_json', row)
        self.assertGreater(row['retrievability'], 0.5)

    def test_suggestions_prefer_own_words_and_exact_match(self):
        helpers.collect('subtle')
        items = app.suggest('sub')
        self.assertEqual(items[0]['word'], 'subtle')
        self.assertTrue(items[0]['own'])
        self.assertEqual(app.suggest('run')[0]['word'], 'run')
        self.assertEqual(app.suggest('!!'), [])
        self.assertLessEqual(len(app.suggest('a')), 8)

    def test_study_day_starts_at_four_in_the_morning(self):
        start = app.day_start(app.study_day(app.now()))
        self.assertEqual(app.study_day(start + timedelta(hours=23, minutes=59)), app.study_day(start))
        self.assertEqual(app.study_day(start + timedelta(hours=24, minutes=1)), app.study_day(start) + timedelta(days=1))
        self.assertEqual(app.study_day(start - timedelta(minutes=1)), app.study_day(start) - timedelta(days=1))

    def test_leech_flag_after_repeated_forgetting(self):
        card_id = helpers.collect('bank')['id']
        with app.connect() as db:
            for _ in range(app.LEECH_FAILURES):
                db.execute('INSERT INTO reviews(card_id,rating,created,log_json) VALUES(?,?,?,?)', (card_id, 1, app.now().isoformat(), '{}'))
        self.assertTrue(app.card_detail(card_id)['card']['progress']['leech'])

    def review_words(self, count, days_ago=0):
        """Record one review each for `count` distinct words on a past study day."""
        when = app.day_start(app.study_day(app.now())) - timedelta(days=days_ago) + timedelta(hours=1)
        with app.connect() as db:
            ids = [r[0] for r in db.execute('SELECT id FROM cards ORDER BY id LIMIT ?', (count,))]
            for card_id in ids:
                db.execute('INSERT INTO reviews(card_id,rating,created,log_json) VALUES(?,?,?,?)', (card_id, 3, when.isoformat(), '{}'))

    def test_daily_goal_progress_counts_distinct_words(self):
        app.update_settings({'daily_goal':3, 'daily_minimum':2})
        for word in ('bank', 'field', 'subtle', 'reluctant'):
            helpers.collect(word)
        goal = app.stats()['goal']
        self.assertEqual((goal['done'], goal['target'], goal['minimum']), (0, 3, 2))
        self.assertFalse(goal['met_minimum'])
        self.assertEqual(goal['to_minimum'], 2)
        card = app.review_next()['card']
        app.rate({'id':card['id'], 'rating':1, 'version':card['card_json']})
        again = app.review_next(focus=card['id'])['card']
        app.rate({'id':again['id'], 'rating':3, 'version':again['card_json']})
        goal = app.stats()['goal']
        self.assertEqual(goal['done'], 1, 'the same word twice counts once')
        for _ in range(2):
            card = app.review_next(last=card['id'])['card']
            app.rate({'id':card['id'], 'rating':3, 'version':card['card_json']})
        goal = app.stats()['goal']
        self.assertTrue(goal['met_minimum'] and goal['met_goal'])
        self.assertEqual(goal['remaining'], 0)

    def test_goal_counts_only_words_remembered(self):
        card_id = helpers.collect('bank')['id']
        helpers.collect('field')
        first = app.review_next(focus=card_id)['card']
        app.rate({'id':card_id, 'rating':1, 'version':first['card_json']})
        goal = app.stats()['goal']
        self.assertEqual((goal['done'], goal['reviewed'], goal['forgot']), (0, 1, 1), '不记得 does not count')
        again = app.review_next(focus=card_id)['card']
        app.rate({'id':card_id, 'rating':2, 'version':again['card_json']})
        goal = app.stats()['goal']
        self.assertEqual((goal['done'], goal['hard'], goal['forgot']), (1, 1, 0), 'recalled later the same day counts')
        other = app.review_next(last=card_id)['card']
        app.rate({'id':other['id'], 'rating':3, 'version':other['card_json']})
        stats = app.stats()
        self.assertEqual((stats['goal']['done'], stats['goal']['good']), (2, 1))
        self.assertEqual(stats['week'][stats['today']], 2)
        self.assertEqual(stats['week_reviewed'][stats['today']], 2)

    def test_only_three_answers_are_accepted_and_old_easy_counts_as_remembered(self):
        card = helpers.collect('bank')
        for bad in (4, 0, '3', True):
            with self.assertRaises(ValueError):
                app.rate({'id':card['id'], 'rating':bad, 'version':card['card_json']})
        with app.connect() as db:
            db.execute('INSERT INTO reviews(card_id,rating,created,log_json) VALUES(?,?,?,?)', (card['id'], 4, app.now().isoformat(), '{}'))
        self.assertEqual(app.stats()['goal']['done'], 1)

    def test_goal_settings_keep_minimum_at_or_below_goal(self):
        self.assertEqual((app.get_settings()['daily_goal'], app.get_settings()['daily_minimum']), (30, 8))
        with self.assertRaises(ValueError):
            app.update_settings({'daily_minimum':31})
        with self.assertRaises(ValueError):
            app.update_settings({'daily_goal':5})
        for bad in ({'daily_goal':0}, {'daily_goal':501}, {'daily_minimum':True}, {'daily_goal':'30'}):
            with self.assertRaises(ValueError):
                app.update_settings(bad)
        self.assertEqual(app.update_settings({'daily_goal':5, 'daily_minimum':5})['daily_goal'], 5)

    def test_top_up_adds_new_words_for_today_only(self):
        app.update_settings({'new_per_day':1})
        for word in ('bank', 'field', 'subtle', 'reluctant'):
            helpers.collect(word)
        self.assertEqual(app.stats()['queue']['new_left'], 1)
        result = app.add_new_today({'count':2})
        self.assertEqual(result['queue']['new_left'], 3)
        self.assertEqual(result['queue']['extra_new'], 2)
        with patch('app.now', return_value=app.now() + timedelta(days=1)):
            self.assertEqual(app.stats()['queue']['extra_new'], 0)
        for bad in (0, -1, True, '2'):
            with self.assertRaises(ValueError):
                app.add_new_today({'count':bad})

    def test_streak_counts_days_that_reach_the_minimum(self):
        app.update_settings({'daily_goal':4, 'daily_minimum':2})
        for word in ('bank', 'field', 'subtle', 'reluctant'):
            helpers.collect(word)
        self.review_words(2, days_ago=1)
        self.review_words(3, days_ago=2)
        self.review_words(1, days_ago=3)   # below the minimum: breaks the chain
        self.review_words(4, days_ago=4)
        stats = app.stats()
        self.assertEqual(stats['streak'], 2, 'today unfinished does not break the streak')
        self.review_words(2, days_ago=0)
        self.assertEqual(app.stats()['streak'], 3)


def Scheduler_no_fuzz(retention):
    from fsrs import Scheduler
    return Scheduler(desired_retention=retention, enable_fuzzing=False)


if __name__ == '__main__':
    unittest.main()
