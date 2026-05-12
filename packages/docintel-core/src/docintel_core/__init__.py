"""docintel-core: shared config, types, and version constants."""

from docintel_core.adapters.factory import make_adapters
from docintel_core.adapters.types import AdapterBundle

__version__ = "0.1.0"

__all__ = ["AdapterBundle", "__version__", "make_adapters"]
