from pprint import pprint

import pychromecast
from ovos_config.config import MycroftUserConfig


def main():
    print(
        """This script will auto configure chromecast devices under your mycroft.conf\nMake sure your devices are turned on and connected to the same Wifi as you, otherwise discovery will fail""")

    print("\nScanning...")
    casts, browser = pychromecast.get_chromecasts()
    for cast in casts:
        print(f"    - Found Chromecast: {cast.cast_info.friendly_name} - {cast.cast_info.host}:{cast.cast_info.port}")

    cfg = MycroftUserConfig()

    devices = [cast.cast_info.friendly_name for cast in casts]
    if not devices:
        print("ERROR: no chromecast devices found")
        exit(1)

    print(f"\nFound devices: {devices}")
    if len(devices) == 1:
        default = 0
    else:
        for idx, d in enumerate(devices):
            print(f"{idx} - {d}")
        default = int(input("select default chromecast device:"))

    for idx, d in enumerate(devices):
        normd = d.lower().replace(" ", "-").strip()
        if "media" not in cfg:
            cfg["media"] = {}
        if "audio_players" not in cfg["media"]:
            cfg["media"]["audio_players"] = {}
        if "video_players" not in cfg["media"]:
            cfg["media"]["video_players"] = {}

        if idx == default:
            if "Audio" not in cfg:
                cfg["Audio"] = {}
            if "backends" not in cfg["Audio"]:
                cfg["Audio"]["backends"] = {}
            cfg["Audio"]["backends"]["chromecast-" + normd] = {
                "type": "ovos_chromecast",
                "identifier": d,
                "active": True
            }

        cfg["media"]["audio_players"]["chromecast-" + normd] = {
            "module": "ovos-media-audio-plugin-chromecast",
            "identifier": d,
            "aliases": [d.replace("-", " ")],
            "active": True
        }
        cfg["media"]["video_players"]["chromecast-" + normd] = {
            "module": "ovos-media-video-plugin-chromecast",
            "identifier": d,
            "aliases": [d.replace("-", " ")],
            "active": True
        }
    cfg.store()

    print("\nmycroft.conf updated!")

    print("\n# Legacy Audio Service:")
    pprint(cfg["Audio"])

    print("\n# ovos-media Service:")
    pprint(cfg["media"])


if __name__ == "__main__":
    main()
