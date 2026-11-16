"""Edifier R990BT specific values (firmware 1.0.2), found with the diagnostic tool."""

SOURCE_GROUP = 0x06

SOURCES = {
    0x01: "Bluetooth",
    0x02: "Line 1",
    0x03: "Line 2",
}

VOLUME_MAX = 16

# EQ presets, from the ConneX app (EQ profile 15), in the order ConneX lists them.
# Values are i18n keys.
EQ_PRESETS = {
    0x00: "eq_music",
    0x02: "eq_movie",
    0x01: "eq_game",
}
