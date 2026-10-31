"""Small shared helpers: hashing, JSONL I/O, git metadata, text similarity."""

from .hashing import sha256_bytes, sha256_file, sha256_json, sha256_text
from .jsonl import read_jsonl, write_jsonl
from .textsim import similarity, token_set

__all__ = [
    "sha256_bytes",
    "sha256_file",
    "sha256_json",
    "sha256_text",
    "read_jsonl",
    "write_jsonl",
    "similarity",
    "token_set",
]
