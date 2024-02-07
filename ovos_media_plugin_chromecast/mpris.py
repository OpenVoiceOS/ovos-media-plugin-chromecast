import time
import asyncio
import pychromecast
import pychromecast.controllers.media
import zeroconf
from dbus_next.aio import MessageBus as DbusMessageBus
from dbus_next.constants import BusType
from dbus_next.service import ServiceInterface, method, dbus_property, PropertyAccess
from dbus_next.service import Variant
from ovos_utils.log import LOG
from ovos_utils.ocp import PlayerState, PlaybackType
from pychromecast import Chromecast


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
        cast_info = self.browser.services[uuid]
        LOG.info(
            f"Found cast device '{cast_info.friendly_name}' with UUID {uuid}"
        )
        cast = pychromecast.get_chromecast_from_cast_info(cast_info, zconf=CastListener.zconf)
        listenerMedia = MediaStatusListener(cast_info.friendly_name, cast)
        cast.media_controller.register_status_listener(listenerMedia)
        self.found_devices[cast_info.friendly_name] = cast

    def remove_cast(self, uuid, _service, cast_info):
        """Called when a cast has beeen lost (MDNS info expired or host down)."""
        LOG.info(f"Lost cast device '{cast_info.friendly_name}' with UUID {uuid}")
        if cast_info.friendly_name in self.found_devices:
            self.found_devices.get(cast_info.friendly_name)

    def update_cast(self, uuid, _service):
        """Called when a cast has beeen updated (MDNS info renewed or changed)."""
        LOG.debug(
            f"Updated cast device '{self.browser.services[uuid].friendly_name}' with UUID {uuid}"
        )


class MediaStatusListener(pychromecast.controllers.media.MediaStatusListener):
    """Status media listener"""
    track_changed_callback = None
    track_stop_callback = None
    bad_track_callback = None

    def __init__(self, name, cast: Chromecast, dbus_type="session"):
        self.name = name
        self.cast = cast
        self.state = PlayerState.STOPPED
        self.uri = None
        self.image = None
        self.playback = PlaybackType.UNDEFINED
        self.duration = 0
        self.ts = 0
        self.title = ""

        self.identity = f"Chromecast{cast.uuid}"
        self.dbus = None
        self.dbus_type = BusType.SYSTEM if dbus_type == "system" else BusType.SESSION
        self.mediaPlayer2Interface = _MediaPlayer2Interface(cast, 'org.mpris.MediaPlayer2')
        self.mediaPlayer2PlayerInterface = _MediaPlayer2PlayerInterface(self, 'org.mpris.MediaPlayer2.Player')

        asyncio.run(self.connect_dbus())

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
            self.ts = time.time()
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

    @property
    def track_position(self):
        """
        get current position in seconds
        """
        if not self.ts:
            return 0
        return (time.time() - self.ts)

    # MPRIS
    @property
    def mpris_metadata(self) -> dict:
        """
        Return dict data used by MPRIS
        """
        meta = {"xesam:url": Variant('s', self.uri),
                'xesam:artist': self.name}
        if self.title:
            meta['xesam:title'] = Variant('s', self.title)
        if self.image:
            meta['mpris:artUrl'] = Variant('s', self.image)
        if self.duration:
            meta['mpris:length'] = Variant('d', self.duration)
        return meta

    async def connect_dbus(self):
        if not self.dbus:
            self.dbus = await DbusMessageBus(bus_type=self.dbus_type).connect()
            await self._export_to_dbus()

    async def _export_to_dbus(self):
        self.dbus.export('/org/mpris/MediaPlayer2', self.mediaPlayer2Interface)
        self.dbus.export('/org/mpris/MediaPlayer2', self.mediaPlayer2PlayerInterface)
        await self.dbus.request_name(f'org.mpris.MediaPlayer2.{self.identity}')


class _MediaPlayer2Interface(ServiceInterface):
    def __init__(self, chromecast: Chromecast, name='org.mpris.MediaPlayer2'):
        self._identity = f"Chromecast.{chromecast.uuid}"
        self._desktopEntry = "Chromecast"
        self._supportedMimeTypes = ["audio/mpeg", "audio/x-mpeg", "video/mpeg", "video/x-mpeg", "video/mpeg-system",
                                    "video/x-mpeg-system", "video/mp4", "audio/mp4", "video/x-msvideo",
                                    "video/quicktime", "application/ogg", "application/x-ogg", "video/x-ms-asf",
                                    "video/x-ms-asf-plugin", "application/x-mplayer2", "video/x-ms-wmv",
                                    "video/x-google-vlc-plugin", "audio/wav", "audio/x-wav", "audio/3gpp", "video/3gpp",
                                    "audio/3gpp2", "video/3gpp2", "video/divx", "video/flv", "video/x-flv",
                                    "video/x-matroska", "audio/x-matroska", "application/xspf+xml"]
        self._supportedUriSchemes = ["file", "http", "https", "rtsp", "realrtsp", "pnm", "ftp", "mtp", "smb", "mms",
                                     "mmsu", "mmst", "mmsh", "unsv", "itpc", "icyx", "rtmp", "rtp", "dccp", "dvd",
                                     "vcd"]
        self._canQuit = True
        self._hasTrackList = False
        self.cast = chromecast
        super().__init__(name)

    def update_props(self, props):
        self.emit_properties_changed(props)

    @dbus_property(access=PropertyAccess.READ)
    def Identity(self) -> 's':
        return self._identity

    @dbus_property(access=PropertyAccess.READ)
    def DesktopEntry(self) -> 's':
        return self._desktopEntry

    @dbus_property(access=PropertyAccess.READ)
    def SupportedMimeTypes(self) -> 'as':
        return self._supportedMimeTypes

    @dbus_property(access=PropertyAccess.READ)
    def SupportedUriSchemes(self) -> 'as':
        return self._supportedUriSchemes

    @dbus_property(access=PropertyAccess.READ)
    def HasTrackList(self) -> 'b':
        return False

    @dbus_property(access=PropertyAccess.READ)
    def CanQuit(self) -> 'b':
        return self._canQuit

    @dbus_property(access=PropertyAccess.READ)
    def CanSetFullscreen(self) -> 'b':
        return False

    @dbus_property(access=PropertyAccess.READ)
    def Fullscreen(self) -> 'b':
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanRaise(self) -> 'b':
        return False

    @method()
    def Quit(self):
        if self._canQuit:
            self.cast.disconnect()


class _MediaPlayer2PlayerInterface(ServiceInterface):
    def __init__(self, media: MediaStatusListener, name):
        super().__init__(name)
        self.status = media

    @property
    def chromecast(self):
        return self.status.cast

    @dbus_property(access=PropertyAccess.READ)
    def Metadata(self) -> 'a{sv}':
        if self.status.state != PlayerState.STOPPED:
            return self.status.mpris_metadata
        return {}

    @dbus_property(access=PropertyAccess.READ)
    def PlaybackStatus(self) -> 's':
        if self.status.state == PlayerState.PLAYING:
            return "Playing"
        if self.status.state == PlayerState.PAUSED:
            return "Paused"
        return "Stopped"

    @dbus_property(access=PropertyAccess.READ)
    def LoopStatus(self) -> 's':
        return "None"

    @dbus_property(access=PropertyAccess.READ)
    def Shuffle(self) -> 'b':
        return False

    @dbus_property(access=PropertyAccess.READ)
    def Volume(self) -> 'd':
        return 1.0

    @dbus_property(access=PropertyAccess.READ)
    def Rate(self) -> 'd':
        return 1

    @dbus_property(access=PropertyAccess.READ)
    def Position(self) -> 'd':
        return self.status.track_position

    @dbus_property(access=PropertyAccess.READ)
    def CanPlay(self) -> 'b':
        return self.status.state == PlayerState.PAUSED

    @dbus_property(access=PropertyAccess.READ)
    def CanPause(self) -> 'b':
        return self.status.state == PlayerState.PLAYING

    @dbus_property(access=PropertyAccess.READ)
    def CanSeek(self) -> 'b':
        return False

    @dbus_property(access=PropertyAccess.READ)
    def CanGoNext(self) -> 'b':
        return False

    @dbus_property(access=PropertyAccess.READ)
    def CanGoPrevious(self) -> 'b':
        return False

    @dbus_property(access=PropertyAccess.READ)
    def CanControl(self) -> 'b':
        return True

    @method()
    def Stop(self):
        if self.chromecast.media_controller.is_playing:
            self.chromecast.media_controller.stop()

    @method()
    def Play(self):
        if self.chromecast.media_controller.is_paused:
            self.chromecast.media_controller.play()

    @method()
    def Pause(self):
        if not self.chromecast.media_controller.is_paused:
            self.chromecast.media_controller.pause()

    @method()
    def PlayPause(self):
        if self.chromecast.media_controller.is_paused:
            self.chromecast.media_controller.play()
        else:
            self.chromecast.media_controller.pause()
