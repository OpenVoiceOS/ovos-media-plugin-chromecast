"""The legacy ovos-audio loader finds and builds the Chromecast backend."""
import logging
import unittest
from unittest.mock import patch

from ovos_plugin_manager.audio import (find_audio_service_plugins,
                                       setup_audio_service)
from ovos_utils.fakebus import FakeBus

from ovos_media_plugin_chromecast.audio import ChromecastAudioService


class TestLegacyLoader(unittest.TestCase):
    @patch("ovos_media_plugin_chromecast.media.CastListener.start_browser")
    def test_setup_audio_service_builds_backend(self, _browser):
        module = find_audio_service_plugins()["ovos_chromecast"]
        config = {"backends": {"tv": {"type": "ovos_chromecast",
                                      "identifier": "Living Room TV"}}}
        services = setup_audio_service(module, config=config, bus=FakeBus())
        self.assertIsInstance(services, list)
        self.assertEqual(len(services), 1)
        self.assertIsInstance(services[0], ChromecastAudioService)
        self.assertEqual(services[0].name, "tv")

    @patch("ovos_media_plugin_chromecast.media.CastListener.start_browser")
    def test_play_without_device_logs_and_returns(self, _browser):
        module = find_audio_service_plugins()["ovos_chromecast"]
        config = {"backends": {"tv": {"type": "ovos_chromecast",
                                      "identifier": "test"}}}
        service = setup_audio_service(module, config=config, bus=FakeBus())[0]
        service.add_list(["http://example.com/a.mp3"])
        with self.assertLogs(level="ERROR") as logs, \
                patch("ovos_media_plugin_chromecast.media.LOG", logging.getLogger("cc")):
            self.assertIsNone(service.play())
        self.assertIn("Unknown Chromecast device: test", logs.output[0])
        self.assertFalse(service.chromecast.is_playing)

if __name__ == "__main__":
    unittest.main()
