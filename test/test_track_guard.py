"""The subsystem guard in ``on_track_start``.

Two instances of the backend exist, one per subsystem. The guard that makes
each ignore the other's tracks has two branches, so the truth table is
pinned here.
"""
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

# ``pychromecast`` is network-bound and heavy, and the plugin imports it at
# module load. CastListener subclasses AbstractCastListener, so that base
# must be a real class, as in test_backends.py.
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

from ovos_utils.ocp import PlaybackType, PlayerState  # noqa: E402 - the stubs above must be in place first

from ovos_media_plugin_chromecast import media as media_mod  # noqa: E402 - the stubs above must be in place first


class TestVideoAudioGuard(unittest.TestCase):
    """``on_track_start``'s subsystem guard.

    Two instances of the backend exist, one per subsystem, and each must
    ignore the other's tracks. The truth table is the contract.
    """

    @staticmethod
    def _service(is_video):
        svc = SimpleNamespace()
        svc.on_track_start = (
            lambda data: media_mod.ChromecastBaseService.on_track_start(
                svc, data))
        svc.on_track_end = lambda data: None
        svc.video = is_video
        svc.identifier = "dev"
        svc.is_playing = True
        svc.meta = {"uri": None}
        svc._now_playing = "http://example.invalid/a.mp3"
        svc._track_start_callback = None
        svc.ts = 0
        return svc

    def _run(self, is_video, playback):
        svc = self._service(is_video)
        svc.on_track_start({"name": "dev",
                            "uri": "http://example.invalid/a.mp3",
                            "playback": playback, "duration": 0,
                            "image": None, "state": PlayerState.PLAYING})
        # The guard returns before meta.update(); reaching it is the only
        # observable difference.
        return "playback" in svc.meta

    def test_each_subsystem_handles_only_its_own_playback(self):
        self.assertTrue(self._run(True, PlaybackType.VIDEO),
                        "the video backend must handle a video track")
        self.assertTrue(self._run(False, PlaybackType.AUDIO),
                        "the audio backend must handle an audio track")

    def test_each_subsystem_ignores_the_other(self):
        self.assertFalse(self._run(True, PlaybackType.AUDIO),
                         "the video backend must ignore an audio track")
        self.assertFalse(self._run(False, PlaybackType.VIDEO),
                         "the audio backend must ignore a video track")


if __name__ == "__main__":
    unittest.main()
