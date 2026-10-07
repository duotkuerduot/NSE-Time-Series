# Integration tests

Storage, recorded provider responses and publishing. The object-store tests that need an S3
endpoint use moto and live in `tests/unit/test_object_stores.py` until Phase 1 adds SQLite.
