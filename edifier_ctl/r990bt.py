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


# --- Custom EQ (6-band parametric, confirmed on firmware 1.0.2) ---
# The speaker stores a frequency per band; these centres work well and match
# the values ConneX would send. Gains are signed dB, clamped to +/-EQ_GAIN_LIMIT.
EQ_BANDS_HZ = (60, 150, 400, 1000, 4000, 12000)
EQ_GAIN_LIMIT = 6
EQ_CUSTOM_LABEL_KEY = "eq_custom"  # i18n key for the "Custom EQ" entry

# Built-in starting points. Users can edit these and save their own.
# Conservative on purpose: the R990BT amplifier clips with large low-band
# boosts, so bass is kept to +2 at most and peaks to +3. Users can push the
# sliders further (up to +/-6) at their own risk.
DEFAULT_EQ_PROFILES = {
    "Flat": (0, 0, 0, 0, 0, 0),
    "Rock": (2, 1, -1, 0, 1, 2),
    "Pop": (1, 1, 0, 1, 1, 0),
    "Instrumental": (1, 0, 1, 1, 2, 1),
    "Vocal": (-1, 0, 2, 2, 1, 0),
    "Bass boost": (2, 2, 0, 0, 0, 0),
    "Treble boost": (0, 0, 0, 1, 2, 2),
}


def clamp_gains(gains) -> tuple[int, ...]:
    """Six integers, each within +/-EQ_GAIN_LIMIT."""
    out = [0] * len(EQ_BANDS_HZ)
    for i in range(len(out)):
        try:
            out[i] = max(-EQ_GAIN_LIMIT, min(EQ_GAIN_LIMIT, int(gains[i])))
        except (IndexError, TypeError, ValueError):
            out[i] = 0
    return tuple(out)


def custom_eq_frames(gains):
    """Yield the (opcode, payload) pairs that set a full custom EQ: one per band."""
    import edifier_ctl.protocol as p

    gains = clamp_gains(gains)
    for band, (freq, gain) in enumerate(zip(EQ_BANDS_HZ, gains)):
        payload = bytes([band, (freq >> 8) & 0xFF, freq & 0xFF, gain & 0xFF])
        yield p.OP_CUSTOM_EQ_SET, payload
