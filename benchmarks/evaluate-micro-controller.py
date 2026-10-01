"""Compatibility entry point for the isolated tiny-controller pilot."""
from pathlib import Path
import runpy

_implementation = Path(__file__).resolve().parents[1] / 'experimental/benchmark/evaluate-micro-controller.py'
if __name__ == '__main__':
    runpy.run_path(str(_implementation), run_name='__main__')
else:
    globals().update({key: value for key, value in runpy.run_path(str(_implementation)).items()
                      if not key.startswith('__')})
