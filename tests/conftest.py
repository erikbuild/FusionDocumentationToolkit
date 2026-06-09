# ABOUTME: Pytest configuration — puts the repo root on sys.path so tests
# ABOUTME: can import the explode module without packaging.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
