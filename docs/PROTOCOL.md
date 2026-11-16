# R990BT BLE protocol

Technical reference for the control protocol used by this project and by the EDIFIER ConneX app.

The speaker has two independent Bluetooth radios:

- **Classic Bluetooth (A2DP)** carries the audio.
- **Bluetooth LE** carries control commands. This is what ConneX, and this app, use.

Commands are framed like this:

```text
AA EC <opcode> <length: 2 bytes> <payload> <checksum>    request
BB EC <opcode> <length: 2 bytes> <payload> <checksum>    reply
```

The checksum is the low byte of the sum of all preceding bytes.

## R990BT reference

Verified on an R990BT with firmware 1.0.2. Each change was set, acknowledged and read back.

| | Value |
|---|---|
| BLE name | `EDIFIER BLE` |
| Advertised UUID | `0000d300-0000-1000-8000-00805f9b34fb` |
| GATT service | `4809d301-1a48-11e9-ab14-d663bd873d93` |
| Notify characteristic | `48090001-1a48-11e9-ab14-d663bd873d93` |
| Write characteristic | `48090002-1a48-11e9-ab14-d663bd873d93` |

| Function | Query | Set | Values |
|---|---|---|---|
| Input | `AA EC 61 00 00 F7` → `<group> <input>` | `AA EC 62 00 02 06 <input> <chk>` | group `06`; `01` Bluetooth, `02` Line 1, `03` Line 2 |
| Volume | `AA EC 66 00 00 FC` → `<max> <current>` | `AA EC 67 00 01 <vol> <chk>` | 0 to 16 |
| EQ preset | `AA EC D5 00 00 6B` → `<preset>` | `AA EC C4 00 01 <preset> <chk>` | `00` Music, `02` Movie, `01` Game |
| Name | `AA EC C9 00 00 5F` | `AA EC CA <len> <UTF-8 name> <chk>` | up to 30 bytes |
| Prompt tone | `AA EC F9 00 00 8F` → `<state>` | `AA EC FA 00 01 <state> <chk>` | `00` off, `01` on |
| Firmware | `AA EC C6 00 00 5C` | | 3 bytes |
| Capabilities | `AA EC D8 00 00 6E` | | 22 bytes |
| Power off | | `AA EC CE 00 00 64` | no reply; the speaker turns off |
| Disconnect audio | | `AA EC CD 00 00 63` | no reply; pairing mode, BLE drops for 1-2 min |

After an input change the speaker also sends `0xC3` notifications with the state of the Bluetooth audio link.

## Power and standby

`0xCE` puts the speaker in standby, the same as holding the knob (the manual calls it standby mode). Once off, it stops advertising over BLE and cannot be reached, and reconnecting Bluetooth audio from Windows does not wake it. It has to be turned back on with the rear knob, so the speaker can be switched off from the PC but not on.

Capabilities payload on the tested unit:

```text
00 00 01 02 01 01 01 00 00 00 01 01 0A 0F 01 00 00 22 00 03 00 00
```

## Other Edifier speakers

The control service of ConneX speakers follows the pattern `4809xxxx-1a48-11e9-ab14-d663bd873d93`, so the scan, info and watch commands may work on other models. Input and EQ codes differ per model: run `watch` and turn the knob to find them. If the speaker doesn't answer at all, [ANDROID_CAPTURE.md](ANDROID_CAPTURE.md) explains how to capture what ConneX sends.
