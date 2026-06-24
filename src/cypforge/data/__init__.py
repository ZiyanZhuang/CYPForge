"""Bundled CYPForge data files.

This package marker exists so that ``importlib.resources.files("cypforge.data")``
resolves to a regular package rather than a namespace package. Without it,
wheel-installed builds of ``cypforge`` cannot locate ``heme_params/`` reliably
when the parent ``cypforge`` namespace is split across multiple distributions.
"""
