import os
import sys

# Ensure src/ is on python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from test_remote_server import mcp

if __name__ == "__main__":
    mcp.run()
