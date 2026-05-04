"""Maven Central version registry adapter."""

from gradle_deps_monitor.infrastructure.registries._base import MavenMetadataRegistry


class MavenCentralRegistry(MavenMetadataRegistry):
    """Looks up versions from ``repo1.maven.org/maven2``."""

    _BASE_URL = "https://repo1.maven.org/maven2"
    _CACHE_PREFIX = "mvn_central"
