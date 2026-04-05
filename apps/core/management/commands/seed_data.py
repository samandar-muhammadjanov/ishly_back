"""Management command entry point for seed_data."""

import os
import sys

# Allow importing from scripts/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
))))

from scripts.seed_data import Command as SeedCommand  # noqa: E402


class Command(SeedCommand):
    """Seed the database with realistic demo data."""
    pass
