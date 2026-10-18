"""Deterministic synthetic sample dataset, for `--sample` and for CI."""

from nsefc.sample.generator import GENERATOR_VERSION, generate

__all__ = ["GENERATOR_VERSION", "generate"]
