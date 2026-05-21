"""
pytest configuration and fixtures for the test suite.
Adds the parent directory to sys.path so tests can import from core/ and ui/.
"""

import sys
from pathlib import Path

# Add the project root to sys.path so imports work
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
