"""Stub pychromecast and zeroconf before any test imports the plugin.

The plugin subclasses ``AbstractCastListener`` and ``MediaStatusListener``,
so both bases are real classes. The rest of the package is a MagicMock.
"""
import sys
from unittest.mock import MagicMock

_pychromecast = MagicMock()
_pychromecast.discovery.AbstractCastListener = type(
    "AbstractCastListener", (), {})
_pychromecast.controllers.media.MediaStatusListener = type(
    "MediaStatusListener", (), {})
sys.modules["pychromecast"] = _pychromecast
sys.modules["pychromecast.discovery"] = _pychromecast.discovery
sys.modules["pychromecast.controllers"] = _pychromecast.controllers
sys.modules["pychromecast.controllers.media"] = _pychromecast.controllers.media
sys.modules["zeroconf"] = MagicMock()
