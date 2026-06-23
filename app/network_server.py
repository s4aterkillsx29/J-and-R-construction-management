"""Compatibility entrypoint for J & R Construction Manager web hosting.

Start Center and Windows launch scripts call `python -m app.network_server`.
The real Flask application now lives in `app.live_server` so this entrypoint stays
small, reliable, and easy to test.
"""
from app.live_server import app, run

if __name__ == "__main__":
    run()
