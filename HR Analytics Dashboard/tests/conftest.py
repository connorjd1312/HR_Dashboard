import os
import sys

# Make the project root (the dir containing core/ and ui/) importable so tests
# can do `from core import analytics` regardless of where pytest is invoked.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
