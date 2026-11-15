"""Edifier R990BT specific values (firmware 1.0.2), found with the diagnostic tool."""

SOURCE_GROUP = 0x06

SOURCES = {
    0x01: "Bluetooth",
    0x02: "Line 1",
    0x03: "Line 2",
}

VOLUME_MAX = 16

# The R990BT has three preset EQs. Which code is which ConneX preset
# (music, movie, game) has not been confirmed yet.
EQ_PRESETS = {
    0x00: "Preset 1",
    0x01: "Preset 2",
    0x02: "Preset 3",
}
