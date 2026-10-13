"""Keep generated diagnostic files outside the source tree."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'app'))
REPORTS = ROOT / 'data' / 'reports'
SAMPLES = ROOT / 'data' / 'samples'
REPORTS.mkdir(parents=True, exist_ok=True)
SAMPLES.mkdir(parents=True, exist_ok=True)
