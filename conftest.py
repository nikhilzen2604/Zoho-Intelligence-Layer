import os
import sys

# Put src/ on sys.path so tests can `import classifier`, `import mapping`, etc.
# The app modules now live under src/.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
