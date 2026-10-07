# Parser golden tests (Phase 2)

One folder per provider and parser version: the expected parse of each archived source file,
plus the file's SHA-256 (ENGINEERING.md 9.3). The source files themselves are licensed
third-party documents, so they stay in the private bucket and are fetched in CI with a
read-only token; only expected outputs and hashes are committed here.
