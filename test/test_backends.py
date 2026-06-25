"""Unit tests for the Chromecast backends.

``pychromecast`` (and ``zeroconf``) are not available in CI, so they are
mocked in ``sys.modules`` before importing the plugin. The tests assert
wiring/contract, not real playback: both the new ovos-media backends and the
legacy ovos-audio adapter build, expose the right base classes, and the
supported URIs + entry points are declared correctly.
"""
import sys
import unittest
from unittest.mock import MagicMock


# --- mock pychromecast/zeroconf so the plugin imports without real deps -----
# CastListener subclasses pychromecast.discovery.AbstractCastListener, so that
# base must be a *real* class (a MagicMock base would swallow the subclass's
# class-level attributes like ``found_devices``).
_pychromecast = MagicMock()


class _AbstractCastListener:
    pass


_pychromecast.discovery.AbstractCastListener = _AbstractCastListener
sys.modules.setdefault("pychromecast", _pychromecast)
sys.modules.setdefault("pychromecast.controllers", _pychromecast.controllers)
sys.modules.setdefault("pychromecast.controllers.media",
                       _pychromecast.controllers.media)
sys.modules.setdefault("pychromecast.discovery", _pychromecast.discovery)
sys.modules.setdefault("zeroconf", MagicMock())

from ovos_plugin_manager.templates.media import (
    RemoteAudioPlayerBackend, RemoteVideoPlayerBackend)
from ovos_plugin_manager.templates.audio import AudioBackend

from ovos_media_plugin_chromecast.media import (
    ChromecastBaseService, ChromecastOCPAudioService,
    ChromecastOCPVideoService)
from ovos_media_plugin_chromecast.audio import (
    ChromecastAudioService, load_service)
from ovos_media_plugin_chromecast.ccast import CastListener


# the backends require an 'identifier' in config and look the device up in
# CastListener.found_devices; seed a fake device so supported_uris() works
_IDENTIFIER = "Living Room TV"
_CFG = {"identifier": _IDENTIFIER}


def _seed_device():
    CastListener.found_devices[_IDENTIFIER] = MagicMock()


def _clear_devices():
    CastListener.found_devices.clear()


class TestNewBackends(unittest.TestCase):
    def setUp(self):
        _seed_device()

    def tearDown(self):
        _clear_devices()

    def test_audio_backend_is_remoteaudioplayerbackend(self):
        svc = ChromecastOCPAudioService(_CFG, bus=MagicMock())
        self.assertIsInstance(svc, RemoteAudioPlayerBackend)
        self.assertIsInstance(svc, ChromecastBaseService)
        self.assertFalse(svc.video)

    def test_video_backend_is_remotevideoplayerbackend(self):
        svc = ChromecastOCPVideoService(_CFG, bus=MagicMock())
        self.assertIsInstance(svc, RemoteVideoPlayerBackend)
        self.assertIsInstance(svc, ChromecastBaseService)
        self.assertTrue(svc.video)

    def test_supported_uris(self):
        svc = ChromecastOCPAudioService(_CFG, bus=MagicMock())
        # device is discovered -> http/https are advertised
        self.assertEqual(svc.supported_uris(), ['http', 'https'])

    def test_supported_uris_no_device(self):
        _clear_devices()
        svc = ChromecastOCPAudioService(_CFG, bus=MagicMock())
        # no discovered device -> nothing is playable
        self.assertEqual(svc.supported_uris(), [])

    def test_missing_identifier_raises(self):
        with self.assertRaises(ValueError):
            ChromecastOCPAudioService({}, bus=MagicMock())


class TestLegacyAdapter(unittest.TestCase):
    def setUp(self):
        _seed_device()

    def tearDown(self):
        _clear_devices()

    def test_legacy_is_audiobackend(self):
        svc = ChromecastAudioService(_CFG, bus=MagicMock(), name='chromecast')
        self.assertIsInstance(svc, AudioBackend)
        # wraps the new OCP backend
        self.assertIsInstance(svc.chromecast, ChromecastOCPAudioService)
        self.assertTrue(hasattr(svc, "play"))
        self.assertTrue(hasattr(svc, "lower_volume"))

    def test_supported_uris(self):
        svc = ChromecastAudioService(_CFG, bus=MagicMock(), name='chromecast')
        self.assertEqual(svc.supported_uris(), ['http', 'https'])

    def test_load_service_builds_active_chromecast_backends(self):
        cfg = {"backends": {
            "mycast": {"type": "chromecast", "active": True,
                       "identifier": _IDENTIFIER},
            "off": {"type": "chromecast", "active": False,
                    "identifier": _IDENTIFIER},
            "other": {"type": "vlc", "active": True},
        }}
        services = load_service(cfg, bus=MagicMock())
        self.assertEqual(len(services), 1)
        self.assertIsInstance(services[0], ChromecastAudioService)

    def test_load_service_empty(self):
        self.assertEqual(load_service({"backends": {}}, bus=MagicMock()), [])


class TestEntryPoints(unittest.TestCase):
    """Both the new and legacy entry-point groups must be declared."""

    def test_setup_declares_new_and_legacy_groups(self):
        import os
        here = os.path.dirname(os.path.dirname(__file__))
        with open(os.path.join(here, "setup.py")) as f:
            setup_src = f.read()
        self.assertIn("opm.media.audio", setup_src)
        self.assertIn("opm.media.video", setup_src)
        self.assertIn("mycroft.plugin.audioservice", setup_src)
        self.assertIn(
            "ovos_media_plugin_chromecast.media:ChromecastOCPAudioService",
            setup_src)
        self.assertIn(
            "ovos_media_plugin_chromecast.media:ChromecastOCPVideoService",
            setup_src)
        self.assertIn("ovos_media_plugin_chromecast.audio", setup_src)


if __name__ == "__main__":
    unittest.main()
