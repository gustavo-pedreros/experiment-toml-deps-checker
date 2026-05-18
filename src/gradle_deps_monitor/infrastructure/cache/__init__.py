"""On-disk cache helpers (RFC-0029).

This package owns the *path* and *lifecycle* concerns of the persistent
``diskcache.Cache`` layers used by registries, scanners, and fetchers.
The cache adapters themselves remain in their feature subpackages
(:mod:`...registries`, :mod:`...scanners`) — only the directory
resolution and bulk-clear operations live here.
"""
