"""Shared fixtures: every test runs against a disposable data folder."""
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app  # noqa: E402


class TempData:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_dir = app.DATA_DIR
        app.DATA_DIR = Path(self.temp.name)
        app.initialize()

    def tearDown(self):
        app.DATA_DIR = self.original_dir
        self.temp.cleanup()


def collect(word, context='', source='', **_ignored):
    """Look a word up and add it to the collection, as the page's save button does."""
    result = app.dictionary_explain({'query':word, 'context':context, 'source':source, 'save':True})
    assert result.get('saved_card'), f'{word} could not be collected'
    return result['saved_card']


def full_row(card_id):
    """The complete stored card, including the explanation snapshot."""
    with app.connect() as db:
        return dict(db.execute('SELECT * FROM cards WHERE id=?', (card_id,)).fetchone())
