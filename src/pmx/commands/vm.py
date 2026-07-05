"""VM (QEMU) command group."""

from pmx.commands._guests import build_guest_app

app = build_guest_app("qemu")
