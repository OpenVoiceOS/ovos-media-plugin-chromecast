# ovos-media-plugin-chromecast

chromecast plugin for [ovos-audio](https://github.com/OpenVoiceOS/ovos-audio) and [ovos-media](https://github.com/OpenVoiceOS/ovos-media)

## Install

`pip install ovos-media-plugin-chromecast`

## MPRIS

This plugin only allows you to initiate playback in a chromecast, if you want to control your chromecasts when playback is initiated externally, you can install [cast_control](https://github.com/alexdelorenzo/cast_control) on your system to provide a MPRIS interface

![imagem](https://github.com/OpenVoiceOS/ovos-media-plugin-chromecast/assets/33701864/b1c7de47-750c-478a-9ebe-15d4076eb71c)

ovos-media will then be able to seamlessly integrate with your chromecast at all times

## Configuration

The easiest way is to use the provided `ovos-chromecast-autoconfigure` command

```bash
$ ovos-chromecast-autoconfigure
This script will auto configure chromecast devices under your mycroft.conf
Make sure your devices are turned on and connected to the same Wifi as you, otherwise discovery will fail

Scanning...
    - Found Chromecast: Bedroom TV - 192.168.1.17:8009

Found devices: ['Bedroom TV']

mycroft.conf updated!

# Legacy Audio Service:
{'backends': {'chromecast-bedroom-tv': {'active': True,
                                        'identifier': 'Bedroom TV',
                                        'type': 'ovos_chromecast'}}}

# ovos-media Service:
{'audio_players': {'chromecast-bedroom-tv': {'active': True,
                                             'aliases': ['Bedroom TV'],
                                             'identifier': 'Bedroom TV',
                                             'module': 'ovos-media-audio-plugin-chromecast'}}},
 'video_players': {'chromecast-bedroom-tv': {'active': True,
                                             'aliases': ['Bedroom TV'],
                                             'identifier': 'Bedroom TV',
                                             'module': 'ovos-media-video-plugin-chromecast'}}}
```

### ovos-audio

```javascript
{
  "Audio": {
    "backends": {
      "my_chromecast": {
        "type": "ovos_chromecast",
        "identifier": "device_name_in_chromecast",
        "active": true
      }
    }
  }
}
```


### ovos-media

> **WARNING**: `ovos-media' has not yet been released, WIP

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
