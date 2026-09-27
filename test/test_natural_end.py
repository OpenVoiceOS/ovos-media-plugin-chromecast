"""Regression tests for the Chromecast MediaBackend v2 event reporting.

Chromecast is an external-events backend: the pychromecast status listener
reports IDLE transitions with an ``idle_reason``, and this plugin has to
turn those into the right ``PlaybackEvent``:

- idle_reason FINISHED (natural end, chromecast finished on its own) ->
  ``END_OF_MEDIA``, via the base ``report_track_end`` helper.
- idle_reason ERROR (chromecast/pychromecast failure) -> ``ERROR``, also
  via ``report_track_end``.
- any other idle_reason with ``stop()`` having been called since the last
  report -> our own stop reached the device -> ``STOPPED``, via
  ``report_track_end`` (``_stop_requested`` resolves the flag correctly).
- any other idle_reason with no ``stop()`` call pending -> the Cast app (or
  some other controller) stopped playback -> ``STOPPED``, reported
  directly: ``report_track_end``'s two-way mapping (flag -> STOPPED,
  no-flag -> END_OF_MEDIA) cannot express this third case, since the
  listener already knows this is neither a natural end nor an error.

None of these paths emit any ``ovos.common_play.*`` bus message: v2
backends report physical events only, the daemon owns the wire.

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

from ovos_plugin_manager.templates.media import PlaybackEvent

from ovos_media_plugin_chromecast.media import ChromecastOCPAudioService
from ovos_media_plugin_chromecast.ccast import CastListener

_IDENTIFIER = "Living Room TV"
_CFG = {"identifier": _IDENTIFIER}


class _Recorder:
    """A bound recording reporter: records every (event, data) call."""

    def __init__(self):
        self.calls = []

    def __call__(self, event, **data):
        self.calls.append((event, data))


class TestChromecastEventReporting(unittest.TestCase):

    def setUp(self):
        CastListener.found_devices[_IDENTIFIER] = MagicMock()

    def tearDown(self):
        CastListener.found_devices.clear()

    def _service(self):
        # a plugin is free to use self.bus for private ecosystem protocols,
        # but MUST NOT emit ovos.common_play.* state on it - a MagicMock bus
        # lets the tests assert .emit was never called over a full verb
        # cycle, which is stronger than watching for specific topics.
        bus = MagicMock()
        reporter = _Recorder()
        service = ChromecastOCPAudioService(_CFG, bus=bus)
        service.bind_event_reporter(reporter)
        uri = "http://example.com/track.mp3"
        service.load_track(uri)
        service.is_playing = True
        # cast.media_controller.is_playing must be truthy for _stop() to
        # actually issue the pychromecast stop() call
        service.cast.media_controller.is_playing = True
        return service, reporter, bus, uri

    def test_stop_is_renamed_to_underscore_stop(self):
        """stop() is now concrete on MediaBackend (sets _stop_requested,
        then calls _stop()); plugins implement _stop(), not stop()."""
        from ovos_media_plugin_chromecast.media import ChromecastBaseService
        self.assertIn("_stop", ChromecastBaseService.__dict__,
                       "ChromecastBaseService must implement _stop()")
        self.assertNotIn("stop", ChromecastBaseService.__dict__,
                          "stop() must not be overridden by the plugin - "
                          "only _stop() - so MediaBackend.stop() keeps "
                          "setting _stop_requested")

    def test_natural_end_finished_idle_reports_end_of_media(self):
        service, reporter, bus, uri = self._service()

        # simulate the MediaStatusListener firing on_track_end because the
        # chromecast reported end of playback on its own (idle_reason
        # FINISHED), no stop() ever called
        service.on_track_end({"name": _IDENTIFIER, "uri": uri})

        events = [event for event, _ in reporter.calls]
        self.assertEqual(events, [PlaybackEvent.END_OF_MEDIA],
                          f"natural end-of-media must report only END_OF_MEDIA; saw: {events}")
        data = dict(reporter.calls[0][1])
        self.assertEqual(data.get("uri"), uri)
        self.assertFalse(service._stop_requested)
        bus.emit.assert_not_called()

    def test_error_idle_reports_error(self):
        service, reporter, bus, uri = self._service()

        service.on_track_error({"name": _IDENTIFIER, "uri": uri})

        events = [event for event, _ in reporter.calls]
        self.assertEqual(events, [PlaybackEvent.ERROR],
                          f"idle_reason ERROR must report only ERROR; saw: {events}")
        data = dict(reporter.calls[0][1])
        self.assertIsInstance(data.get("error"), str)
        self.assertEqual(data.get("uri"), uri)
        self.assertFalse(service._stop_requested)
        bus.emit.assert_not_called()

    def test_our_stop_reaching_device_reports_stopped(self):
        """service.stop() sets _stop_requested; the device eventually goes
        IDLE with a non-FINISHED reason, routed to on_track_stopped, which
        must resolve the flag to STOPPED (not END_OF_MEDIA)."""
        service, reporter, bus, uri = self._service()

        service.stop()  # concrete MediaBackend.stop(): sets flag, calls _stop()
        self.assertTrue(service._stop_requested)
        service.on_track_stopped({"name": _IDENTIFIER, "uri": uri})

        events = [event for event, _ in reporter.calls]
        self.assertEqual(events, [PlaybackEvent.STOPPED],
                          f"our own stop() must report only STOPPED; saw: {events}")
        data = dict(reporter.calls[0][1])
        self.assertEqual(data.get("uri"), uri)
        self.assertFalse(service._stop_requested,
                          "the flag must be cleared after being resolved")
        bus.emit.assert_not_called()

    def test_external_stop_without_our_stop_reports_stopped_not_end_of_media(self):
        """The Cast app (or any other controller) stops playback: the
        device goes IDLE with a non-FINISHED reason, but *we* never called
        stop(), so _stop_requested is False. report_track_end's two-way
        mapping would misreport this as END_OF_MEDIA; the fix reports
        STOPPED directly for this case instead."""
        service, reporter, bus, uri = self._service()

        self.assertFalse(service._stop_requested)
        service.on_track_stopped({"name": _IDENTIFIER, "uri": uri})

        events = [event for event, _ in reporter.calls]
        self.assertEqual(events, [PlaybackEvent.STOPPED],
                          f"external stop must report STOPPED, not END_OF_MEDIA; saw: {events}")
        data = dict(reporter.calls[0][1])
        self.assertEqual(data.get("uri"), uri)
        self.assertFalse(service._stop_requested)
        bus.emit.assert_not_called()

    def test_full_verb_cycle_never_emits_bus_state(self):
        """play/pause/resume/our-stop/error, driven through the
        external-event listener callbacks exactly as pychromecast would
        call them, must never put anything on self.bus - only report()
        calls are allowed."""
        service, reporter, bus, uri = self._service()

        service.on_track_start({"name": _IDENTIFIER, "uri": uri,
                                 "playback": service.meta["playback"]})
        service.on_track_paused({"name": _IDENTIFIER, "uri": uri})
        service.on_track_resumed({"name": _IDENTIFIER, "uri": uri})
        service.is_playing = True  # on_track_stopped resets is_playing
        service.stop()
        service.on_track_stopped({"name": _IDENTIFIER, "uri": uri})
        service.is_playing = True
        service.on_track_error({"name": _IDENTIFIER, "uri": uri})

        bus.emit.assert_not_called()
        events = [event for event, _ in reporter.calls]
        self.assertEqual(events, [
            PlaybackEvent.TRACK_START,
            PlaybackEvent.PAUSED,
            PlaybackEvent.RESUMED,
            PlaybackEvent.STOPPED,
            PlaybackEvent.ERROR,
        ])
        error_data = dict(reporter.calls[events.index(PlaybackEvent.ERROR)][1])
        self.assertIsInstance(error_data.get("error"), str)


if __name__ == "__main__":
    unittest.main()
