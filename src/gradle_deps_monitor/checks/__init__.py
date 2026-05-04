"""Pluggable rules (catalog health, deprecations).

Each rule is a self-contained module that imports from
:mod:`gradle_deps_monitor.domain` and emits ``Finding`` objects. Rules live
outside :mod:`gradle_deps_monitor.application` because they are extension
points, not core orchestration.
"""
