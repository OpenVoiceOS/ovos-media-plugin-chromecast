# ovos-media-plugin-chromecast

This plugin adds Chromecast support to [ovos-audio](https://github.com/OpenVoiceOS/ovos-audio) and [ovos-media](https://github.com/OpenVoiceOS/ovos-media).

## Install

```bash
pip install ovos-media-plugin-chromecast
```

## MPRIS

This plugin can start playback on a Chromecast. It cannot control a Chromecast when another device starts the playback.

To control a Chromecast in that case, install [cast_control](https://github.com/alexdelorenzo/cast_control) on your system. It provides an MPRIS interface.

![cast_control MPRIS interface](https://github.com/OpenVoiceOS/ovos-media-plugin-chromecast/assets/33701864/b1c7de47-750c-478a-9ebe-15d4076eb71c)

With `cast_control` running, ovos-media integrates with your Chromecast at all times.

## Configuration

Run the `ovos-chromecast-autoconfigure` command to configure your Chromecast devices automatically.

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

You can also configure the plugin by hand.

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

> **WARNING**: `ovos-media` has not released yet. This section is a work in progress.

```javascript
{
 "media": {

    // PlaybackType.AUDIO handlers
    "audio_players": {
        // the chromecast player uses a headless chromecast instance to handle uris
        "kitchen_chromecast": {
            // the plugin name
            "module": "ovos-media-audio-plugin-chromecast",

            // this must match the name of the chromecast device
            "identifier": "Kitchen Chromecast",

            // users can request specific handlers in an utterance
            // by using these aliases
             "aliases": ["kitchen chromecast", "kitchen"],

            // set to false to deactivate this handler
            "active": true
        }
    },

    // PlaybackType.VIDEO handlers
    "video_players": {
        // the chromecast player uses a headless chromecast instance to handle uris
        "living_room_chromecast": {
            // the plugin name
            "module": "ovos-media-video-plugin-chromecast",

            // this must match the name of the chromecast device
            "identifier": "Living Room Chromecast",

            // users can request specific handlers in an utterance
            // by using these aliases
             "aliases": ["Living Room Chromecast", "Living Room"],

            // set to false to deactivate this handler
            "active": true
        }
    }
}
```

## Related projects

- [ovos-audio](https://github.com/OpenVoiceOS/ovos-audio): the legacy audio service this plugin's backend targets
- [ovos-media](https://github.com/OpenVoiceOS/ovos-media): the media service this plugin's player targets
- [cast_control](https://github.com/alexdelorenzo/cast_control): provides MPRIS control for externally started Chromecast playback
