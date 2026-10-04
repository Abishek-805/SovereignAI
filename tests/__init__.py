# Compatibility namespace for archived test helpers; production never imports these.
from pathlib import Path
__path__.append(str(Path(__file__).resolve().parents[1] / '_review_for_deletion' / 'tests'))
