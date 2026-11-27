"""The legacy ovos-audio loader finds and builds the Chromecast backend."""
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


if __name__ == "__main__":
    unittest.main()
