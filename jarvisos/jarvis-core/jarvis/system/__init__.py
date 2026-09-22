"""Hardware/OS control backends. Each module degrades gracefully when its
tools (nmcli, bluetoothctl, wpctl…) are missing — queries return
'unknown' instead of raising, actions return (ok, message)."""
