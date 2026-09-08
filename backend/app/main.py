import os
import sys
import importlib

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import main

# Ensure main is fresh on reloads
importlib.reload(main)
app = main.app

