import sys
from pathlib import Path

# All services share "app" as their top-level package name. When multiple
# services are installed in the same venv, whichever was installed first wins
# sys.path priority. Inserting this service's root at position 0 ensures the
# correct "app" is resolved regardless of installation order.
_root = str(Path(__file__).parent)
if _root not in sys.path:
    sys.path.insert(0, _root)
