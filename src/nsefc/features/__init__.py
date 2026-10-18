"""Features: scale-free, as-of only, windows in trading sessions.

Feature code reaches data only through ``load_panel(as_of=T)`` (rule L1) and may not import
``nsefc.targets`` (rule L2, enforced by import-linter).
"""

from nsefc.features.build import FeatureSpec, build, window_flags
from nsefc.features.panel import LeakageError, Panel, load_panel

__all__ = ["FeatureSpec", "LeakageError", "Panel", "build", "load_panel", "window_flags"]
