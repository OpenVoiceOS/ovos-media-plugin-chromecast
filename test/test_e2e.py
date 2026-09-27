"""End-to-end tests: drive the real Chromecast OCP backend through a real
``OCPMediaPlayer`` on a FakeBus via ovoscope's media harness.

The Chromecast *engine* (``pychromecast`` + the discovered cast device) is
mocked so no real network/device is needed, but everything else is real: the
OCP player routes play/pause/resume/stop to ``ChromecastOCPAudioService``
exactly as ovos-media would at runtime.

``ChromecastOCPAudioService`` is a ``RemoteAudioPlayerBackend``: it does not
play audio itself, it casts to a remote device. Playback *state* is still
reported synchronously because ``MediaBackend.ocp_start()`` emits
``PlayerState.PLAYING`` on the bus *before* delegating to ``backend.play()``,
so the harness can assert PLAYING/PAUSED/STOPPED just like a local backend.

The injected device mock makes ``cast.wait()`` and
``cast.media_controller.play_media()/stop()/pause()/play()`` non-blocking
no-ops, which is required because ovos-media calls ``backend.play()``
synchronously on the bus thread.

Requires ``ovoscope[media]`` (pulls ovos-media).
"""
import sys
import unittest
from unittest.mock import MagicMock, patch

# NOTE: the installed ovoscope[media] harness (OCPPlayerHarness) predates the
# MediaBackend v2 template - it wires backends through the removed
# ``set_track_start_callback`` API (see ovoscope/media.py ~:400), so it
# raises AttributeError against any v2 backend rather than exercising it.
# Skipped until ovoscope ships a v2-aware harness; do not delete these tests,
# they document the intended end-to-end contract.
try:
    from ovoscope import OCPPlayerHarness
    from ovos_utils.ocp import MediaEntry, PlaybackType, PlayerState
    HAVE_HARNESS = True
except Exception:
    HAVE_HARNESS = False

HARNESS_IS_V2_AWARE = False

# ``pychromecast`` is a heavy, network-bound, non-pip-installable engine; mock
# the whole package tree in sys.modules so the plugin (whose ccast.py does
# ``import pychromecast`` at module load) imports cleanly without it.
#
# ccast.py *subclasses* ``pychromecast.discovery.AbstractCastListener`` and
# ``pychromecast.controllers.media.MediaStatusListener``, so those two names
# must be real classes (subclassing a bare MagicMock yields an unusable
# MagicMock, not a class). The rest of the package can stay MagicMock.
_pychromecast = MagicMock()
_discovery = MagicMock()
_discovery.AbstractCastListener = type("AbstractCastListener", (object,), {})
_controllers = MagicMock()
_media = MagicMock()
_media.MediaStatusListener = type("MediaStatusListener", (object,), {})
_pychromecast.discovery = _discovery
_pychromecast.controllers = _controllers
_controllers.media = _media
sys.modules.setdefault("pychromecast", _pychromecast)
sys.modules.setdefault("pychromecast.discovery", _discovery)
sys.modules.setdefault("pychromecast.controllers", _controllers)
sys.modules.setdefault("pychromecast.controllers.media", _media)
sys.modules.setdefault("zeroconf", MagicMock())

import ovos_media_plugin_chromecast.media as media_mod
from ovos_media_plugin_chromecast.media import ChromecastOCPAudioService

URI = "http://example.com/song.mp3"
DEVICE = "Test Cast"


def _factory(bus):
    """Build the real Chromecast audio backend for injection into the player."""
    return ChromecastOCPAudioService({"identifier": DEVICE}, bus)


def _mock_cast():
    """A non-blocking fake cast device.

    ``wait()`` and the media-controller transport calls must not block (the
    harness drives ``play()`` synchronously on the bus thread); MagicMock
    methods are instant no-ops. ``is_playing`` is truthy so ``stop()`` takes
    the real-stop branch.
    """
    cast = MagicMock()
    cast.media_controller.is_playing = True
    cast.media_controller.is_paused = False
    return cast


@unittest.skipUnless(HAVE_HARNESS, "ovoscope[media] not installed")
@unittest.skipUnless(HARNESS_IS_V2_AWARE,
                      "installed ovoscope OCPPlayerHarness predates "
                      "MediaBackend v2 (calls set_track_start_callback)")
class TestChromecastEndToEnd(unittest.TestCase):
    def test_play_pause_resume_stop_through_ocp(self):
        cast = _mock_cast()
        # The backend discovers its device via ``CastListener.found_devices``
        # and kicks off discovery in __init__; mock both so no real network /
        # zeroconf browser is touched and ``self.cast`` resolves to our fake.
        with patch.object(media_mod.CastListener, "start_browser"), \
                patch.object(media_mod.CastListener, "stop_discovery"), \
                patch.object(media_mod.CastListener, "found_devices",
                             {DEVICE: cast}):
            with OCPPlayerHarness(backend_factory=_factory) as h:
                entry = MediaEntry(uri=URI, playback=PlaybackType.AUDIO)

                h.play(entry)
                h.assert_player_state(PlayerState.PLAYING)
                h.assert_now_playing_uri(URI)
                # the real backend actually cast the uri to the (mocked) device
                self.assertEqual(h.backend._now_playing, URI)
                cast.media_controller.play_media.assert_called_once()

                h.pause()
                h.assert_player_state(PlayerState.PAUSED)

                h.resume()
                h.assert_player_state(PlayerState.PLAYING)

                h.stop()
                h.assert_player_state(PlayerState.STOPPED)

    def test_backend_is_the_real_chromecast_plugin(self):
        cast = _mock_cast()
        with patch.object(media_mod.CastListener, "start_browser"), \
                patch.object(media_mod.CastListener, "stop_discovery"), \
                patch.object(media_mod.CastListener, "found_devices",
                             {DEVICE: cast}):
            with OCPPlayerHarness(backend_factory=_factory) as h:
                self.assertIsInstance(h.backend, ChromecastOCPAudioService)
                self.assertEqual(h.backend.supported_uris(),
                                 ["http", "https"])


if __name__ == "__main__":
    unittest.main()
