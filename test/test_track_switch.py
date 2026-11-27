"""A load while a track plays, driven through the real status listener.

The device reports BUFFERING and PLAYING as one state, so a new track does
not pass through STOPPED. TRACK_START must still fire for it, and the end of
the replaced track must carry the replaced uri.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from ovos_plugin_manager.templates.media import PlaybackEvent

from ovos_media_plugin_chromecast.ccast import CastListener, MediaStatusListener
from ovos_media_plugin_chromecast.media import ChromecastOCPAudioService

DEVICE = "Living Room TV"
A = "http://example.com/a.mp3"
B = "http://example.com/b.mp3"


def _status(player_state, uri, idle_reason=None, duration=120.0):
    return SimpleNamespace(player_state=player_state, content_id=uri,
                           content_type="audio/mpeg", duration=duration,
                           images=[], idle_reason=idle_reason)


class TestTrackSwitch(unittest.TestCase):

    def setUp(self):
        CastListener.found_devices[DEVICE] = MagicMock()
        self.service = ChromecastOCPAudioService({"identifier": DEVICE},
                                                 bus=MagicMock())
        self.calls = []
        self.service.bind_event_reporter(
            lambda event, **data: self.calls.append((event, data.get("uri"))))
        self.listener = MediaStatusListener(DEVICE, MagicMock())

    def tearDown(self):
        CastListener.found_devices.clear()

    def _play(self, uri):
        self.service.load_track(uri)
        self.service.play()

    def test_switch_without_idle_reports_track_start_for_each_track(self):
        self._play(A)
        self.listener.new_media_status(_status("BUFFERING", A))
        self.listener.new_media_status(_status("PLAYING", A))
        self._play(B)
        self.listener.new_media_status(_status("BUFFERING", B))
        self.listener.new_media_status(_status("PLAYING", B))
        self.assertEqual(self.calls, [(PlaybackEvent.TRACK_START, A),
                                      (PlaybackEvent.TRACK_START, B)])

    def test_switch_with_interrupted_idle_reports_old_uri(self):
        self._play(A)
        self.listener.new_media_status(_status("PLAYING", A))
        self._play(B)
        self.listener.new_media_status(_status("IDLE", B, "INTERRUPTED"))
        self.listener.new_media_status(_status("BUFFERING", B))
        self.listener.new_media_status(_status("PLAYING", B))
        self.assertEqual(self.calls, [(PlaybackEvent.TRACK_START, A),
                                      (PlaybackEvent.END_OF_MEDIA, A),
                                      (PlaybackEvent.TRACK_START, B)])
        # the replaced track's end leaves the new track playing
        self.assertTrue(self.service.is_playing)

    def test_switch_then_natural_end_reports_new_uri(self):
        self._play(A)
        self.listener.new_media_status(_status("PLAYING", A))
        self._play(B)
        self.listener.new_media_status(_status("PLAYING", B))
        self.listener.new_media_status(_status("IDLE", None, "FINISHED"))
        self.assertEqual(self.calls[-1], (PlaybackEvent.END_OF_MEDIA, B))

    def test_load_failure_before_start_reports_error_for_the_track(self):
        self._play(A)
        self.listener.load_media_failed(None, 104)
        self.assertEqual(self.calls, [(PlaybackEvent.ERROR, A)])
        self.assertFalse(self.service.is_playing)

    def test_resume_is_not_a_track_start(self):
        self._play(A)
        self.listener.new_media_status(_status("PLAYING", A))
        self.listener.new_media_status(_status("PAUSED", A))
        self.listener.new_media_status(_status("PLAYING", A))
        self.assertEqual([e for e, _ in self.calls],
                         [PlaybackEvent.TRACK_START, PlaybackEvent.PAUSED,
                          PlaybackEvent.RESUMED])


class TestTrackLengthAndPosition(unittest.TestCase):

    def setUp(self):
        CastListener.found_devices[DEVICE] = MagicMock()
        self.service = ChromecastOCPAudioService({"identifier": DEVICE},
                                                 bus=MagicMock())
        self.listener = MediaStatusListener(DEVICE, MagicMock())

    def tearDown(self):
        CastListener.found_devices.clear()

    def _start(self, duration):
        self.service.load_track(A)
        self.service.play()
        self.listener.new_media_status(_status("PLAYING", A,
                                               duration=duration))

    def test_nothing_plays_gives_none(self):
        self.assertIsNone(self.service.get_track_length())
        self.assertIsNone(self.service.get_track_position())

    def test_known_length_in_milliseconds(self):
        self._start(120.5)
        self.assertEqual(self.service.get_track_length(), 120500)
        self.assertGreaterEqual(self.service.get_track_position(), 0)

    def test_live_stream_length_is_minus_one(self):
        self._start(None)
        self.assertEqual(self.service.get_track_length(), -1)

    def test_after_end_gives_none(self):
        self._start(120.0)
        self.listener.new_media_status(_status("IDLE", None, "FINISHED"))
        self.assertIsNone(self.service.get_track_length())
        self.assertIsNone(self.service.get_track_position())


if __name__ == "__main__":
    unittest.main()
