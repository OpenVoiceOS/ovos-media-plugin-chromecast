# Copyright 2017 Mycroft AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import time
from mimetypes import guess_type

import pychromecast
import pychromecast.controllers.media
import zeroconf

from ovos_plugin_manager.templates.media import MediaBackend, RemoteAudioPlayerBackend, RemoteVideoPlayerBackend
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
        LOG.info(
            f"Found cast device '{self.browser.services[uuid].friendly_name}' with UUID {uuid}"
        )
        cast = pychromecast.get_chromecast_from_cast_info(self.browser.services[uuid], zconf=CastListener.zconf)
        self.found_devices[self.browser.services[uuid].friendly_name] = cast

        listenerMedia = MediaStatusListener(self.browser.services[uuid].friendly_name, cast)
        cast.media_controller.register_status_listener(listenerMedia)

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


class ChromecastBaseService(MediaBackend):
    """
        Backend for playback on chromecast. Using the default media
        playback controller included in pychromecast.
    """

    def __init__(self, config, bus=None, video=False):
        super().__init__(config, bus)
        self.video = video
        self.connection_attempts = 0
        self.bus = bus
        self.config = config

        if self.config is None or 'identifier' not in self.config:
            raise ValueError("Chromecast identifier not set!")  # Can't connect since no id is specified
        else:
            self.identifier = self.config['identifier']

        MediaStatusListener.track_stop_callback = self.on_track_end
        MediaStatusListener.bad_track_callback = self.on_track_error
        MediaStatusListener.track_changed_callback = self.on_track_start
        CastListener.start_browser()

        self.meta = {"name": self.identifier,
                     "uri": None,
                     "duration": 0,
                     "playback": PlaybackType.VIDEO if self.video else PlaybackType.AUDIO}
        self.is_playing = False
        self.ts = 0

    def reset_metadata(self):
        self.is_playing = False  # not plugin initiated
        self.ts = 0
        self.meta = {"name": self.identifier,
                     "uri": None,
                     "duration": 0,
                     "playback": PlaybackType.VIDEO if self.video else PlaybackType.AUDIO}

    def on_track_start(self, data):
        if not self.is_playing:
            return  # not plugin initiated

        # it's other device
        if data["name"] != self.identifier:
            return

        # check if track changed in our device
        if self.meta["uri"] is not None and \
                data["uri"] != self.meta["uri"]:
            # TODO - end of media, or just update OCP info ?
            LOG.info(f"Chromecast track changed externally: {data}")
            self.on_track_end(self.meta)
            return

        # check if it's video or audio playback
        # 2 instances of this class might exist, one for each subsystem
        if self.video and data["playback"] != PlaybackType.VIDEO:
            return
        elif not self.video and data["playback"] == PlaybackType.VIDEO:
            return

        # check if this is our track, trigger callback
        if data["uri"] == self._now_playing and data != self.meta:
            LOG.info(f"Chromecast playback started: {data}")
            self.meta = data
            self.ts = time.time()
            if self._track_start_callback:
                self._track_start_callback(self.track_info().get('name', f"{self.identifier} Chromecast"))

    def on_track_end(self, data):
        if not self.is_playing:
            return  # not plugin initiated
        if data["name"] != self.identifier:
            return
        if data["uri"] == self.meta["uri"]:
            LOG.info(f"End of media: {data}")
            self.reset_metadata()

        self._now_playing = None
        if self._track_start_callback:
            self._track_start_callback(None)

    def on_track_error(self, data):
        if not self.is_playing:
            return  # not plugin initiated
        LOG.warning(f"Chromecast error: {data}")
        self.reset_metadata()
        self.ocp_error()

    def supported_uris(self):
        """ Return supported uris of chromecast. """
        if self.cast:
            return ['http', 'https']
        else:
            return []

    @property
    def cast(self):
        if self.identifier in CastListener.found_devices:
            return CastListener.found_devices[self.identifier]
        return None

    def play(self, repeat=False):
        """ Start playback."""

        cast = self.cast
        if cast is None:
            raise RuntimeError(f"Unknown Chromecast device: {self.identifier}")

        cast.wait()  # Make sure the device is ready to receive command

        track = self._now_playing
        self.meta = {"name": self.identifier,
                     "playback": PlaybackType.VIDEO if self.video else PlaybackType.AUDIO,
                     "uri": track}

        mime = guess_type(track)[0] or 'audio/mp3'
        self.is_playing = True
        cast.media_controller.play_media(track, mime)

    def stop(self):
        """ Stop playback and quit app. """
        self.reset_metadata()
        if self.cast is not None and self.cast.media_controller.is_playing:
            self.cast.media_controller.stop()
            return True
        else:
            return False

    def pause(self):
        """ Pause current playback. """
        if self.cast is not None and not self.cast.media_controller.is_paused:
            self.cast.media_controller.pause()

    def resume(self):
        if self.cast is not None and self.cast.media_controller.is_paused:
            self.cast.media_controller.play()

    def lower_volume(self):
        if self.cast is not None:
            self.cast.volume_down()

    def restore_volume(self):
        if self.cast is not None:
            self.cast.volume_up()

    def shutdown(self):
        """ Disconnect from the device. """
        self.reset_metadata()
        if self.cast is not None:
            self.cast.disconnect()
        CastListener.stop_discovery()

    def get_track_length(self):
        """
        getting the duration of the audio in milliseconds
        """
        return self.meta.get("duration", self.get_track_position()) * 1000

    def get_track_position(self):
        """
        get current position in milliseconds
        """
        if not self.ts:
            return 0
        return (time.time() - self.ts) * 1000  # calculate approximate

    def set_track_position(self, milliseconds):
        """
        go to position in milliseconds

          Args:
                milliseconds (int): number of milliseconds of final position
        """
        if self.cast is not None and self.cast.media_controller.is_playing:
            self.cast.media_controller.seek(milliseconds / 1000)


class ChromecastOCPAudioService(RemoteAudioPlayerBackend, ChromecastBaseService):
    def __init__(self, config, bus=None):
        super().__init__(config, bus, video=False)


class ChromecastOCPVideoService(RemoteVideoPlayerBackend, ChromecastBaseService):
    def __init__(self, config, bus=None):
        super().__init__(config, bus, video=True)


if __name__ == "__main__":
    from ovos_utils.fakebus import FakeBus

    s = ChromecastOCPAudioService({"identifier": 'Side door TV'}, bus=FakeBus())
    s.load_track("https://archive.org/download/SporesBBCr4/1%20Growth.mp3")
    time.sleep(5)
    s.play()
    from ovos_utils import wait_for_exit_signal

    wait_for_exit_signal()
