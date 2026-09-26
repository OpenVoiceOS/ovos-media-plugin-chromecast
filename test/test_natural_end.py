"""Regression test: a track that ends naturally (the chromecast device
reports the end of playback on its own, via the MediaStatusListener's
track_stop_callback -> on_track_end, no stop() ever called) must report
MediaState.END_OF_MEDIA / PlayerState.STOPPED on the bus, exactly like an
explicit stop does.

``pychromecast``/``zeroconf`` are not available in CI, so they are mocked
in ``sys.modules`` before importing the plugin, matching test_backends.py.
"""
import sys
import unittest
from unittest.mock import MagicMock

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

from ovos_utils.fakebus import FakeBus
from ovos_utils.ocp import MediaState, PlayerState

from ovos_media_plugin_chromecast.media import ChromecastOCPAudioService
from ovos_media_plugin_chromecast.ccast import CastListener

_IDENTIFIER = "Living Room TV"
_CFG = {"identifier": _IDENTIFIER}


class TestNaturalEndOfMedia(unittest.TestCase):

    def setUp(self):
        CastListener.found_devices[_IDENTIFIER] = MagicMock()

    def tearDown(self):
        CastListener.found_devices.clear()

    def _service(self):
        bus = FakeBus()
        states = []
        player_states = []
        bus.on("ovos.common_play.media.state",
               lambda msg: states.append(msg.data.get("state")))
        bus.on("ovos.common_play.player.state",
               lambda msg: player_states.append(msg.data.get("state")))
        service = ChromecastOCPAudioService(_CFG, bus=bus)
        service._now_playing = "http://example.com/track.mp3"
        service.is_playing = True
        service.meta["uri"] = service._now_playing
        return service, states, player_states

    def test_natural_track_end_emits_end_of_media(self):
        service, states, player_states = self._service()

        # simulate the MediaStatusListener firing on_track_end because the
        # chromecast reported end of playback on its own, no stop() called
        service.on_track_end({"name": _IDENTIFIER, "uri": service.meta["uri"]})

        self.assertIn(MediaState.END_OF_MEDIA, states,
                       f"natural end-of-media never emitted END_OF_MEDIA; saw: {states}")
        self.assertIn(PlayerState.STOPPED, player_states,
                       f"natural end-of-media never emitted PlayerState.STOPPED; saw: {player_states}")


if __name__ == "__main__":
    unittest.main()
