from discordrpc import RPC
from .config import get_config

config = get_config()

app = RPC(
    app_id=config.get("appid") or 1436573238636576891,
    exit_if_discord_close=False,
    exit_on_disconnect=False
)

app.run()

# Use dbus to query gapless.
# Will concat a property when called.
command = "dbus-send --print-reply --dest=org.mpris.MediaPlayer2.com.github.neithern.g4music /org/mpris/MediaPlayer2 org.freedesktop.DBus.Properties.Get string:'org.mpris.MediaPlayer2.Player' string: "
