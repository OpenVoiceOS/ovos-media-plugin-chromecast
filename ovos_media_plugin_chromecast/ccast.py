import pychromecast
import pychromecast.controllers.media
import zeroconf

from ovos_utils.log import LOG
from ovos_utils.ocp import PlayerState, PlaybackType


class CastListener(pychromecast.discovery.AbstractCastListener):
    """Listener for discovering chromecasts."""
    browser = None
    zconf = None
    found_devices = {}

    @classmethod
    def start_browser(cls):
        if cls.zconf is None:
            cls.zconf = zeroconf.Zeroconf()
        if cls.browser is not None:
            cls.browser.stop_discovery()
        cls.browser = pychromecast.discovery.CastBrowser(cls(), cls.zconf)
        cls.browser.start_discovery()

    @classmethod
    def stop_discovery(cls):
        if cls.browser:
            cls.browser.stop_discovery()

    def add_cast(self, uuid, _service):
        """Called when a new cast has beeen discovered."""
        print(uuid, _service)
        LOG.info(
            f"Found cast device '{self.browser.services[uuid].friendly_name}' with UUID {uuid}"
        )
        cast = pychromecast.get_chromecast_from_cast_info(self.browser.services[uuid], zconf=CastListener.zconf)
        self.found_devices[self.browser.services[uuid].friendly_name] = cast

        listenerMedia = MediaStatusListener(self.browser.services[uuid].friendly_name, cast)
        cast.media_controller.register_status_listener(listenerMedia)

    def remove_cast(self, uuid, _service, cast_info):
        """Called when a cast has been lost (MDNS info expired or host down)."""
        LOG.info(f"Lost cast device '{cast_info.friendly_name}' with UUID {uuid}")
        if cast_info.friendly_name in self.found_devices:
            self.found_devices.get(cast_info.friendly_name)

    def update_cast(self, uuid, _service):
        """Called when a cast has been updated (MDNS info renewed or changed)."""
        LOG.debug(
            f"Updated cast device '{self.browser.services[uuid].friendly_name}' with UUID {uuid}"
        )


class MediaStatusListener(pychromecast.controllers.media.MediaStatusListener):
    """Status media listener"""
    track_changed_callback = None
    track_stop_callback = None
    bad_track_callback = None

    def __init__(self, name, cast):
        self.name = name
        self.cast = cast
        self.state = PlayerState.STOPPED
        self.uri = None
        self.image = None
        self.playback = PlaybackType.UNDEFINED
        self.duration = 0

    def new_media_status(self, status):
        if status.content_type is None:
            self.playback = PlaybackType.UNDEFINED
        elif "audio" in status.content_type:
            self.playback = PlaybackType.AUDIO
        else:
            self.playback = PlaybackType.VIDEO
        if status.player_state in ["PLAYING", 'BUFFERING']:
            state = PlayerState.PLAYING
        elif status.player_state == "PAUSED":
            state = PlayerState.PLAYING
        else:
            state = PlayerState.STOPPED

        self.uri = status.content_id
        self.duration = status.duration or 0
        if status.images:
            self.image = status.images[0].url
        else:
            self.image = None

        # NOTE: ignore callbacks on IDLE, it always happens right before playback
        if self.track_changed_callback and \
                self.state == PlayerState.STOPPED and \
                status.player_state != "IDLE" and \
                state == PlayerState.PLAYING:
            self.track_changed_callback({
                "state": state,
                "duration": self.duration,
                "image": self.image,
                "uri": self.uri,
                "playback": self.playback,
                "name": self.name
            })
        elif self.track_stop_callback and \
                status.idle_reason == "FINISHED" and \
                status.player_state == "IDLE":
            self.track_stop_callback({
                "state": state,
                "duration": self.duration,
                "image": self.image,
                "uri": self.uri,
                "playback": self.playback,
                "name": self.name
            })
            self.uri = None
            self.image = None
            self.duration = 0
            self.playback = PlaybackType.UNDEFINED
        elif self.bad_track_callback and \
                status.idle_reason == "ERROR" and \
                status.player_state == "IDLE":
            pass  # dedicated handler in parent class already
        self.state = state

    def load_media_failed(self, item, error_code):
        self.state = PlayerState.STOPPED
        if self.bad_track_callback:
            self.bad_track_callback({
                "state": self.state,
                "duration": self.duration,
                "image": self.image,
                "uri": self.uri,
                "playback": self.playback,
                "name": self.name
            })
        self.uri = None
        self.image = None
        self.duration = 0
        self.playback = PlaybackType.UNDEFINED
