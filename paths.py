"""Where Leaf finds its files, in source form and as a packaged executable."""
from pathlib import Path
import sys

FROZEN = bool(getattr(sys, 'frozen', False))
# Files bundled inside the executable (web assets, licences) or the source tree.
BUNDLE = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
# The folder the user sees: next to Leaf.exe, or the project folder.
HOME = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent


def data_file(name):
    """Large read-only dictionaries live next to the program, not inside it.

    Keeping ~180 MB of SQLite out of the one-file executable avoids unpacking
    it to a temporary folder on every launch. The bundled copy remains a
    fallback so an older build layout still works.
    """
    beside = HOME / 'data' / name
    return beside if beside.exists() else BUNDLE / 'data' / name
