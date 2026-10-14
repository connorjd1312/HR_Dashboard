import os
import sys

# Make the project root importable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# UI tests need no display
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
