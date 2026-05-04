"""Google Maven version registry adapter."""

from gradle_deps_monitor.infrastructure.registries._base import MavenMetadataRegistry


class GoogleMavenRegistry(MavenMetadataRegistry):
    """Looks up versions from ``dl.google.com/dl/android/maven2``.

    Covers AndroidX, Google Play Services, AGP, Firebase, and all
    artifacts published under the ``com.google.*`` / ``androidx.*`` namespaces.
    """

    _BASE_URL = "https://dl.google.com/dl/android/maven2"
    _CACHE_PREFIX = "google_maven"
