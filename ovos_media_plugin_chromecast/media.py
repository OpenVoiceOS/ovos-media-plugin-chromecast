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

from ovos_plugin_manager.templates.media import (MediaBackend, PlaybackEvent,
                                                  RemoteAudioPlayerBackend,
                                                  RemoteVideoPlayerBackend)
from ovos_utils.log import LOG
from ovos_utils.ocp import PlaybackType

from ovos_media_plugin_chromecast.ccast import MediaStatusListener, CastListener


class ChromecastBaseService(MediaBackend):
    """
        Backend for playback on chromecast. Using the default media
        playback controller included in pychromecast.

        Chromecast is an *external-events* backend: the device itself
        notifies the plugin (via ``MediaStatusListener``, on pychromecast's
        own status-update thread) whenever playback actually starts, pauses,
        resumes, stops or ends - whether that was caused by this plugin's
        own play()/pause()/resume()/stop() calls or by someone controlling
        the same Chromecast from the Cast app. Those callbacks are the only
        place physical ``PlaybackEvent``s are reported; the command methods
        below only issue the corresponding pychromecast call and let the
        listener report what actually happened.
    """

    can_seek = True
    can_pause = True

    def __init__(self, config, bus=None, video=False):
        super().__init__(config, bus)
        self.video = video
        self.connection_attempts = 0

        if self.config is None or 'identifier' not in self.config:
            raise ValueError("Chromecast identifier not set!")  # Can't connect since no id is specified
        else:
            self.identifier = self.config['identifier']

        MediaStatusListener.track_changed_callback = self.on_track_start
        MediaStatusListener.paused_callback = self.on_track_paused
        MediaStatusListener.resumed_callback = self.on_track_resumed
        MediaStatusListener.stopped_callback = self.on_track_stopped
        MediaStatusListener.track_stop_callback = self.on_track_end
        MediaStatusListener.bad_track_callback = self.on_track_error
        CastListener.start_browser()

        self.uri = None
        self.meta = {"name": self.identifier,
                     "uri": None,
                     "title": self.identifier,
                     "thumbnail": "",  # TODO default icon
                     "duration": 0,
                     "playback": PlaybackType.VIDEO if self.video else PlaybackType.AUDIO}
        self.is_playing = False
        self.ts = 0

    def load_track(self, uri: str, metadata: dict = None) -> bool:
        self.uri = uri
        self.meta["uri"] = uri
        if metadata:
            self.meta["title"] = metadata.get("title", self.identifier)
            self.meta["thumbnail"] = metadata.get("thumbnail", "")
            self.meta["duration"] = metadata.get("duration", 0)
        return True

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
            LOG.info(f"Chromecast track changed externally: {data}")
            self.on_track_end({"name": self.identifier, "uri": self.meta["uri"]})
            return

        # check if it's video or audio playback
        # 2 instances of this class might exist, one for each subsystem
        if self.video and data["playback"] != PlaybackType.VIDEO:
            return
        elif not self.video and data["playback"] == PlaybackType.VIDEO:
            return

        # check if this is our track, trigger callback
        if data["uri"] == self.uri and data != self.meta:
            LOG.info(f"Chromecast playback started: {data}")
            self.meta.update(data)
            self.ts = time.time()
            self.report(PlaybackEvent.TRACK_START)

    def on_track_paused(self, data):
        if not self.is_playing:
            return  # not plugin initiated
        if data["name"] != self.identifier:
            return
        LOG.info(f"Chromecast paused: {data}")
        self.report(PlaybackEvent.PAUSED)

    def on_track_resumed(self, data):
        if not self.is_playing:
            return  # not plugin initiated
        if data["name"] != self.identifier:
            return
        LOG.info(f"Chromecast resumed: {data}")
        self.report(PlaybackEvent.RESUMED)

    def on_track_stopped(self, data):
        """Cast device went IDLE for a reason other than FINISHED/ERROR -
        i.e. playback was explicitly stopped, either by our own stop() or
        by someone stopping it from the Cast app.

        ``report_track_end`` can only tell "our stop" from "natural end"
        (its two-way mapping is flag -> STOPPED, no-flag -> END_OF_MEDIA);
        it has no way to express "external stop", which is a third,
        distinct case this listener DOES know how to detect (idle_reason
        is neither FINISHED nor ERROR). So: when we requested the stop,
        delegate to ``report_track_end`` (it reports STOPPED and clears the
        flag correctly). When we did not, the two-way helper would
        misreport this as END_OF_MEDIA - report STOPPED directly instead.
        """
        if not self.is_playing:
            return  # not plugin initiated
        if data["name"] != self.identifier:
            return
        LOG.info(f"Chromecast stopped: {data}")
        uri = self.meta.get("uri")
        self.reset_metadata()
        if self._stop_requested:
            self.report_track_end(uri=uri)
        else:
            self.report(PlaybackEvent.STOPPED, uri=uri)

    def on_track_end(self, data):
        if not self.is_playing:
            return  # not plugin initiated
        if data["name"] != self.identifier:
            return
        uri = self.meta.get("uri")
        if data["uri"] == uri:
            LOG.info(f"End of media: {data}")
        self.reset_metadata()
        # natural end-of-media (idle_reason FINISHED): report_track_end's
        # flag check naturally resolves to END_OF_MEDIA here unless stop()
        # was called at the exact same instant the track finished on its
        # own, in which case reporting STOPPED instead is acceptable.
        self.report_track_end(uri=uri)

    def on_track_error(self, data):
        if not self.is_playing:
            return  # not plugin initiated
        LOG.warning(f"Chromecast error: {data}")
        uri = self.meta.get("uri")
        self.reset_metadata()
        self.report_track_end(uri=uri, error=str(data))

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

        self.meta["uri"] = track = self.uri

        mime = guess_type(track)[0] or 'audio/mp3'
        self.is_playing = True
        cast.media_controller.play_media(track, mime,
                                         thumb=self.meta.get("thumbnail"),
                                         title=self.meta.get("title", track.split("/")[-1]))

    def _stop(self) -> bool:
        """ Stop playback and quit app.

        ``stop()`` (concrete on ``MediaBackend``) sets ``_stop_requested``
        before calling this. Does not reset metadata or report anything
        directly - the device's own status update (picked up by
        ``MediaStatusListener`` and routed to ``on_track_stopped``) is what
        actually reports ``PlaybackEvent.STOPPED``. Resetting ``is_playing``
        here would make that callback's "not plugin initiated" guard drop
        the real event.
        """
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
