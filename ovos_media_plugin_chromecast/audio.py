from ovos_plugin_manager.templates.audio import AudioBackend
from ovos_utils.log import LOG

from ovos_media_plugin_chromecast.media import ChromecastOCPAudioService


class ChromecastAudioService(AudioBackend):
    """
        Chromecast Audio backend - old style plugin for ovos-audio (not ovos-media)
    """

    def __init__(self, config, bus, name='chromecast'):
        super().__init__(config, bus, name)
        self.chromecast = ChromecastOCPAudioService(self.config, bus=self.bus)

    def set_track_start_callback(self, callback_func):
        self.chromecast.set_track_start_callback(callback_func)

    def supported_uris(self):
        return self.chromecast.supported_uris()

    def play(self, repeat=False):
        self.chromecast.play()

    def stop(self):
        self.chromecast.stop()

    def pause(self):
        self.chromecast.pause()

    def resume(self):
        self.chromecast.resume()

    def next(self):
        LOG.error("Chromecast does not support 'next'")

    def previous(self):
        LOG.error("Chromecast does not support 'previous'")

    def lower_volume(self):
        self.chromecast.lower_volume()

    def restore_volume(self):
        self.chromecast.restore_volume()

    def track_info(self):
        """ Extract info of current track. """
        return self.chromecast.meta

    def get_track_length(self) -> int:
        """
        getting the duration of the audio in milliseconds
        """
        # we only can estimate how much we already played as a minimum value
        return self.chromecast.get_track_length()

    def get_track_position(self) -> int:
        """
        get current position in milliseconds
        """
        return self.chromecast.get_track_position()

    def set_track_position(self, milliseconds):
        """
        go to position in milliseconds
          Args:
                milliseconds (int): number of milliseconds of final position
        """
        self.chromecast.set_track_position(milliseconds)


def load_service(base_config, bus):
    backends = base_config.get('backends', {})
    services = [(b, backends[b]) for b in backends
                if backends[b].get('type') in ['chromecast', 'ovos_chromecast'] and
                backends[b].get('active', True)]
    instances = [ChromecastAudioService(s[1], bus, s[0]) for s in services]
    if len(instances) == 0:
        LOG.warning("No Chromecast backends have been configured")
    return instances
