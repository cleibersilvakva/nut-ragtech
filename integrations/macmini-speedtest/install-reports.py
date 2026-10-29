"""Compatibility entry point: deploy only the daily08hchart."""
import runpy
from pathlib import Path
runpy.run_path(str(Path(__file__).with_name('install-chart-reports.py')),run_name='__main__')
