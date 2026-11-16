# What the ConneX app knows about the R990BT

Findings from a static analysis of the EDIFIER ConneX Android app (`com.edifier.edifierconnex`), done to understand how the app talks to the R990BT. No app code is included in this repository; only the facts below.

## Capabilities

The speaker answers query `0xD8` with a capability payload, and ConneX decides which features to show from it, not from the model name. The R990BT (firmware 1.0.2) returns 22 bytes:

```text
00 00 01 02 01 01 01 00 00 00 01 01 0A 0F 01 00 00 22 00 03 00 00
```

| Byte | Value | Meaning in ConneX |
|---|---|---|
| b1 | `00` | No battery display |
| b2 | `01` | Name can be read |
| b3 | `02` | Name can be changed, up to 30 characters |
| b4 | `01` | Classic Bluetooth address can be read |
| b5 | `01` | Firmware version can be read |
| b6 | `01` | Can disconnect Bluetooth audio (A2DP) |
| b7 | `00` | No re-pairing command |
| b8 | `00` | **No "auto shutdown without audio" setting** |
| b9 | `00` | No sleep timer |
| b10 | `01` | Can be powered off |
| b11 | `01` | Shows the user manual |
| b12 | `0A` | Firmware update over BLE, on Android and iOS |
| b13 | `0F` | EQ profile 15 |
| b14 | `01` | UI skin 1 |
| b17 | `22` | Prompt tone on/off; factory reset |
| b19 | `03` | Input switching; volume |
| b20, b21 | `00` | None of the extra features those bytes flag |

The "saving mode" setting lives in byte 23 of the payload. The R990BT payload ends at byte 21, so the speaker does not offer it; querying it (`0xB1`) gets no reply.

## EQ presets

EQ profile 15 has three presets. ConneX lists them in this order:

| Value | Preset |
|---|---|
| `00` | Music |
| `02` | Movie |
| `01` | Game |

## Commands relevant to the R990BT

| Opcode | Purpose | Status |
|---|---|---|
| `0x61` / `0x62` | Input query / set | Verified |
| `0x66` / `0x67` | Volume query / set | Verified |
| `0xD5` / `0xC4` | EQ preset query / set | Verified |
| `0xC9` / `0xCA` | Name query / set | Query verified; set implemented |
| `0xC6` | Firmware version | Verified |
| `0xCE` | Power off | Verified |
| `0xF9` / `0xFA` | Prompt tone on/off query / set | Implemented, from ConneX |
| `0x86` / `0x87` | Multi prompt tone query / set | Not used: the R990BT does not flag it |
| `0xCD` | Disconnect Bluetooth audio | Verified: leaves the speaker in pairing mode |
| `0x07` | Factory reset | Not used, on purpose |
| `0x10` / `0x11` | Firmware update (see below) | Not used, on purpose |
| `0x12` | Not sent or handled anywhere in ConneX | Unknown |

## Auto-mute and standby

ConneX has no setting that controls the speaker's auto-mute. The related features it knows about (auto shutdown without audio, saving mode, sleep timer) are all reported as unsupported by the R990BT. The behaviour is fixed in firmware.

## Firmware updates

The R990BT declares firmware update over BLE. ConneX asks Edifier's server whether an update exists for the product, using the signed-in user's token, and downloads the image if there is one. Whether an update for the R990BT exists can only be seen in the app itself.

### Update protocol (from the decompiled app, not tested)

ConneX's `CommandManager.setOtaReady` / `setOtaStart` and `OtaHelper.handleOta` show the flow:

1. **`0x10` "OTA ready"**, sent by the app. Payload: firmware file size (4 bytes, big-endian), target version (3 bytes, e.g. `01 00 03`), maximum packet size (2 bytes; ConneX uses 512). Firmwares split into MCU and Bluetooth parts add a flag byte `01` and both part sizes (4 + 4 bytes), 18 bytes in total. If the speaker doesn't answer, the app resends it up to three times.
2. **`0x11` from the speaker** asks for data: byte 0 is a status, bytes 1-2 the number of bytes wanted. Status `00` means "send the next block", `02` "resend the last one", `07`-`0A` refer to the MCU or Bluetooth part of a split image and are not treated as errors; anything else is an error and the app aborts.
3. **`0x11` from the app** carries the data: status echoed, a "last block" flag (`01` on the final one), then the bytes.
4. After the last block the speaker verifies the image and restarts; the app waits for it to reconnect and reads the version (`0xC6`) to confirm.

There is no command to cancel an update: the app only resets its own state. A `0x10` with made-up values would announce a file that never arrives; what the firmware does then (time out and resume, or stay waiting until it is powered off) is not visible from the app.

