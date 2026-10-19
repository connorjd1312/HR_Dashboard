import os
import sys

# Make the project root importable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# UI tests need no display
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

# Offscreen Qt cannot find Windows fonts and falls back to a much wider one,
# which makes the layout-width tests measure about 1.6x too wide
if sys.platform == 'win32':
    os.environ.setdefault('QT_QPA_FONTDIR', os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts'))
