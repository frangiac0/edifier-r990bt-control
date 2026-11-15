"""Valores especificos del Edifier R990BT (firmware 1.0.2), obtenidos con la herramienta de diagnostico."""

SOURCE_GROUP = 0x06

SOURCES = {
    0x01: "Bluetooth",
    0x02: "Line 1",
    0x03: "Line 2",
}

VOLUME_MAX = 16

# El R990BT tiene tres ecualizadores predefinidos. Los nombres y el orden de los
# codigos todavia no estan verificados contra la app ConneX.
EQ_PRESETS = {
    0x00: "Preset 1",
    0x01: "Preset 2",
    0x02: "Preset 3",
}
