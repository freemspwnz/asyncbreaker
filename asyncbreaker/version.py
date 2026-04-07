"""Package version metadata."""

__version__ = "2.0.1"
"""The current semantic version string."""

# Public alias (not UPPER_CASE) for consumers who read major.minor only.
short_version = ".".join(__version__.split(".")[:2])  # pylint: disable=invalid-name
"""Major.minor prefix of :data:`__version__`."""
