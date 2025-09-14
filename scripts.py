#!/usr/bin/env python3
"""Development scripts for the Evently Booking Platform."""

import subprocess
import sys
from pathlib import Path


def start():
    """Start the development server."""
    subprocess.run([
        "uvicorn", 
        "evently_booking_platform.main:app", 
        "--host", "0.0.0.0", 
        "--port", "3000", 
        "--reload"
    ])


def lint():
    """Run linting and type checking."""
    subprocess.run(["black", "evently_booking_platform/"])
    subprocess.run(["mypy", "evently_booking_platform/"])


def format_code():
    """Format code with black."""
    subprocess.run(["black", "evently_booking_platform/"])





if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts.py <command>")
        print("Commands: start, lint, format, type-check")
        sys.exit(1)
    
    command = sys.argv[1].replace("-", "_")
    if hasattr(sys.modules[__name__], command):
        getattr(sys.modules[__name__], command)()
    else:
        print(f"Unknown command: {sys.argv[1]}")
        sys.exit(1)