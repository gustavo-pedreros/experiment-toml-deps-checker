"""Application layer.

Use cases that orchestrate the domain. Outbound dependencies are declared as
``Protocol`` interfaces in :mod:`gradle_deps_monitor.application.ports`,
implemented by adapters in :mod:`gradle_deps_monitor.infrastructure`.
"""
