"""Deterministic synthetic sample dataset (§16.3), for `--sample` and for CI."""

from nsefc.sample.generator import GENERATOR_VERSION, generate

__all__ = ["GENERATOR_VERSION", "generate"]
