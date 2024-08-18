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

from ovos_plugin_manager.templates.media import MediaBackend, RemoteAudioPlayerBackend, RemoteVideoPlayerBackend
from ovos_utils.log import LOG
from ovos_utils.ocp import PlaybackType

from ovos_media_plugin_chromecast.ccast import MediaStatusListener, CastListener


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
                     "title": self.identifier,
                     "thumbnail": "",  # TODO default icon
                     "duration": 0,
                     "playback": PlaybackType.VIDEO if self.video else PlaybackType.AUDIO}
        self.is_playing = False
        self.ts = 0

    def load_track(self, uri, metadata: dict = None):
        super().load_track(uri)
        if metadata:
            self.meta["title"] = metadata.get("title", self.identifier)
            self.meta["thumbnail"] = metadata.get("thumbnail", "")
            self.meta["duration"] = metadata.get("duration", 0)

    def reset_metadata(self):
        self.is_playing = False  # not plugin initiated
        self.ts = 0
        self.meta["uri"] = None

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
            self.meta.update(data)
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

        self.meta["uri"] = track = self._now_playing

        mime = guess_type(track)[0] or 'audio/mp3'
        self.is_playing = True
        cast.media_controller.play_media(track, mime,
                                         thumb=self.meta.get("thumbnail"),
                                         title=self.meta.get("title", track.split("/")[-1]))

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
    s.meta = {"title": "Spores: Growth",
              "thumbnail": "https://ia801302.us.archive.org/30/items/SporesBBCr4/Spores.jpg?cnt=0"}
    s.load_track("https://archive.org/download/SporesBBCr4/1%20Growth.mp3")
    time.sleep(5)
    s.play()
    from ovos_utils import wait_for_exit_signal

    wait_for_exit_signal()
