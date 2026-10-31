"""AutoDoctor Data Integration Engine.

A standalone Python project that extracts automotive diagnostic trouble code
(DTC) data from several upstream projects, preserves the raw records, normalizes
them, validates them, detects duplicates and conflicts, and merges the accepted
records into one traceable SQLite database for the AutoDoctor AI Flutter client.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
