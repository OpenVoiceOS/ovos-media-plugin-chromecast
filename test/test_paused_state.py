"""A paused cast must report PAUSED, not PLAYING.

`MediaStatusListener.new_media_status` mapped the device's `"PAUSED"` to
`PlayerState.PLAYING`, so a cast paused from the Google Home app, or from the
device itself, was handed to OCP as still playing. `PlayerState.PAUSED` existed
and was never used.

The suite could not see it. `test_e2e.py` asserts PAUSED on OCP's own state,
which `MediaBackend.ocp_pause()` emits on the bus before it delegates to the
backend, so no cell ever drove the listener's own mapping. These rows drive
`new_media_status` directly, which is the only place the mapping lives.

`pychromecast`/`zeroconf` are not installed in CI, so they are mocked in
`sys.modules` before the import, matching test_natural_end.py.

Two things here exist because of test order, and both were measured rather
than guessed. `ccast` subclasses a name from the mocked `pychromecast`, so if
another module imports it first with a bare MagicMock in place, the "class"
is a mock instance and every row below compares mocks and says nothing. This
module therefore loads `ccast.py` into a private namespace of its own, with a
real base class installed, and leaves the shared import alone. And
`new_media_status` is applied to a stand-in rather than an instance, which is
the idiom test_track_guard.py already uses for `on_track_start`.
"""
import importlib.util
import sys
import unittest
from types import SimpleNamespace
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

from ovos_utils.ocp import PlaybackType, PlayerState  # noqa: E402 - the stubs above must be in place first


class _RealBase:
    """`ccast` subclasses this. A MagicMock here makes the subclass a mock."""


def _load_ccast():
    """Load ccast.py privately, with a real base class under the listener."""
    media_stub = sys.modules["pychromecast.controllers.media"]
    media_stub.MediaStatusListener = _RealBase
    spec = importlib.util.find_spec("ovos_media_plugin_chromecast.ccast")
    private = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(private)
    return private


MediaStatusListener = _load_ccast().MediaStatusListener
assert isinstance(MediaStatusListener, type), MediaStatusListener


def _status(player_state, content_type="audio/mp3", idle_reason=None):
    """The fields `new_media_status` reads off a pychromecast MediaStatus."""
    return SimpleNamespace(player_state=player_state,
                           content_type=content_type,
                           content_id="http://example.invalid/a.mp3",
                           duration=120.0,
                           images=None,
                           idle_reason=idle_reason)


class TestPausedIsPaused(unittest.TestCase):
    def setUp(self):
        self.seen = []
        self.listener = self._listener()

    def _listener(self, record=False):
        """A stand-in carrying the attributes `new_media_status` reads.

        `self.seen.append` is a BOUND method, as the backend's
        `self.on_track_start` is. A plain function here would be re-bound by
        attribute lookup and called with the stand-in as its first argument.
        """
        stand_in = SimpleNamespace(
            name="Living Room",
            state=PlayerState.STOPPED,
            uri=None,
            image=None,
            playback=PlaybackType.UNDEFINED,
            duration=0,
            track_changed_callback=self.seen.append if record else None,
            track_stop_callback=None,
            bad_track_callback=None)
        stand_in.new_media_status = (
            lambda status: MediaStatusListener.new_media_status(stand_in, status))
        return stand_in

    def test_a_paused_device_is_paused(self):
        """The defect: PAUSED was mapped to PLAYING."""
        self.listener.new_media_status(_status("PAUSED"))
        self.assertEqual(PlayerState.PAUSED, self.listener.state)

    def test_a_paused_device_is_not_reported_as_playing(self):
        """Said the other way round, because PAUSED could also be STOPPED.

        A paused cast still holds its track. Reporting STOPPED would be a
        different wrong answer, so the row names both.
        """
        self.listener.new_media_status(_status("PAUSED"))
        self.assertNotEqual(PlayerState.PLAYING, self.listener.state)
        self.assertNotEqual(PlayerState.STOPPED, self.listener.state)

    def test_pausing_does_not_announce_a_track_change(self):
        """A pause is not a new track.

        The track-changed callback fires on a STOPPED -> PLAYING edge. With
        PAUSED mapped to PLAYING, pausing an idle backend's device produced
        that edge and announced a track start that never happened.
        """
        listener = self._listener(record=True)
        listener.new_media_status(_status("PAUSED"))
        self.assertEqual([], self.seen,
                         f"a pause announced a track change: {self.seen}")

    def test_playing_still_announces_a_track_change(self):
        """The control: without it, the row above passes on a dead callback."""
        listener = self._listener(record=True)
        listener.new_media_status(_status("PLAYING"))
        self.assertEqual(1, len(self.seen), "a real play announced nothing")
        self.assertEqual(PlayerState.PLAYING, self.seen[0]["state"])

    def test_the_other_states_are_unchanged(self):
        """PLAYING, BUFFERING and IDLE keep the answers they had."""
        for player_state, expected in (("PLAYING", PlayerState.PLAYING),
                                       ("BUFFERING", PlayerState.PLAYING),
                                       ("IDLE", PlayerState.STOPPED),
                                       ("UNKNOWN", PlayerState.STOPPED)):
            with self.subTest(player_state=player_state):
                listener = self._listener()
                listener.new_media_status(_status(player_state))
                self.assertEqual(expected, listener.state)

    def test_the_playback_type_is_untouched_by_this(self):
        """A guard: the mapping edit must not disturb the content-type branch."""
        self.listener.new_media_status(_status("PAUSED", content_type="video/mp4"))
        self.assertEqual(PlaybackType.VIDEO, self.listener.playback)


if __name__ == "__main__":
    unittest.main()
