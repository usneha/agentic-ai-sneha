"""
Launcher for the Streamlit chat UI.

`streamlit run app.py` imports streamlit (and its protobuf-based deps, e.g.
chromadb's opentelemetry exporter) before app.py's code runs, so setting
PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION inside app.py is too late. This
launcher sets it first, then invokes Streamlit's CLI.

Run:
    uv run python 5_chat/run_app.py
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from streamlit.web import cli as stcli

if __name__ == "__main__":
    sys.argv = ["streamlit", "run", str(Path(__file__).parent / "app.py")] + sys.argv[1:]
    sys.exit(stcli.main())
