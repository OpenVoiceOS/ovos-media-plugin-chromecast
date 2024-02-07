# ovos-media-plugin-chromecast

chromecast plugin for [ovos-media](https://github.com/OpenVoiceOS/ovos-media)


## MPRIS

This plugin only allows you to initiate playback in a chromecast, if you want to control your chromecasts when playback is initiated externally, you can install [cast_control](https://github.com/alexdelorenzo/cast_control) on your system to provide a MPRIS interface

ovos-media will then be able to seamlessly integrate with your chromecast at all times

## Install

`pip install ovos-media-plugin-chromecast`

## Configuration

```javascript
{
 "media": {

    // PlaybackType.AUDIO handlers
    "audio_players": {
        // chromecast player uses a headless chromecast instance to handle uris
        "kitchen_chromecast": {
            // the plugin name
            "module": "ovos-media-audio-plugin-chromecast",
            
            // this needs to be the name of the chromecast device!
            "identifier": "Kitchen Chromecast",

            // users may request specific handlers in the utterance
            // using these aliases
             "aliases": ["kitchen chromecast", "kitchen"],

            // deactivate a plugin by setting to false
            "active": true
        }
    },

    // PlaybackType.VIDEO handlers
    "video_players": {
        // chromecast player uses a headless chromecast instance to handle uris
        "living_room_chromecast": {
            // the plugin name
            "module": "ovos-media-video-plugin-chromecast",

            // this needs to be the name of the chromecast device!
            "identifier": "Living Room Chromecast",
            
            // users may request specific handlers in the utterance
            // using these aliases
             "aliases": ["Living Room Chromecast", "Living Room"],

            // deactivate a plugin by setting to false
            "active": true
        }
    }
}
```
