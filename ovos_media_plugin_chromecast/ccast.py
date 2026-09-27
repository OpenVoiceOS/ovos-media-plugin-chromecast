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
    """Status media listener.

    Fires on the pychromecast status-update thread whenever the *device*
    reports a player-state change, regardless of who caused it - our own
    play()/pause()/resume()/stop() calls, or someone pausing/resuming/
    stopping playback directly from the Cast app. These callbacks are the
    only source of physical playback events for this backend; the
    ``ChromecastBaseService`` methods that issue commands do not report
    anything themselves.
    """
    track_changed_callback = None  # TRACK_START
    paused_callback = None  # PAUSED
    resumed_callback = None  # RESUMED
    stopped_callback = None  # STOPPED (explicit/cancelled, not natural end)
    track_stop_callback = None  # END_OF_MEDIA (natural end, idle_reason FINISHED)
    bad_track_callback = None  # ERROR

    def __init__(self, name, cast):
        self.name = name
        self.cast = cast
        self.state = PlayerState.STOPPED
        self.uri = None
        self.image = None
        self.playback = PlaybackType.UNDEFINED
        self.duration = 0

    def _payload(self, state):
        return {
            "state": state,
            "duration": self.duration,
            "image": self.image,
            "uri": self.uri,
            "playback": self.playback,
            "name": self.name
        }

    def _reset(self):
        self.uri = None
        self.image = None
        self.duration = 0
        self.playback = PlaybackType.UNDEFINED

    def new_media_status(self, status):
        if status.content_type is None:
            self.playback = PlaybackType.UNDEFINED
        elif "audio" in status.content_type:
            self.playback = PlaybackType.AUDIO
        else:
            self.playback = PlaybackType.VIDEO

        if status.player_state in ("PLAYING", "BUFFERING"):
            state = PlayerState.PLAYING
        elif status.player_state == "PAUSED":
            state = PlayerState.PAUSED
        else:
            state = PlayerState.STOPPED

        prev = self.state
        self.uri = status.content_id
        self.duration = status.duration or 0
        self.image = status.images[0].url if status.images else None

        # NOTE: ignore callbacks on IDLE->PLAYING, it always happens right
        # before playback actually starts
        if self.track_changed_callback and prev == PlayerState.STOPPED and \
                status.player_state != "IDLE" and state == PlayerState.PLAYING:
            self.track_changed_callback(self._payload(state))
        elif self.paused_callback and prev == PlayerState.PLAYING and \
                state == PlayerState.PAUSED:
            self.paused_callback(self._payload(state))
        elif self.resumed_callback and prev == PlayerState.PAUSED and \
                state == PlayerState.PLAYING:
            self.resumed_callback(self._payload(state))
        elif status.player_state == "IDLE" and status.idle_reason == "FINISHED":
            if self.track_stop_callback:
                self.track_stop_callback(self._payload(state))
            self._reset()
        elif status.player_state == "IDLE" and status.idle_reason == "ERROR":
            if self.bad_track_callback:
                self.bad_track_callback(self._payload(state))
            self._reset()
        elif status.player_state == "IDLE" and \
                prev in (PlayerState.PLAYING, PlayerState.PAUSED):
            # explicit stop (ours or from the Cast app), not a natural end
            if self.stopped_callback:
                self.stopped_callback(self._payload(state))
            self._reset()

        self.state = state

    def load_media_failed(self, item, error_code):
        self.state = PlayerState.STOPPED
        if self.bad_track_callback:
            self.bad_track_callback(self._payload(self.state))
        self._reset()
