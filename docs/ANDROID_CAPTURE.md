# Capturing ConneX commands on Android

Only needed for a speaker that does not answer the diagnostic commands, or to find commands this project does not support yet. The idea is to record the Bluetooth packets the official app sends while you use it, and copy the exact commands.

## 1. Enable developer options

1. Go to **Settings > About phone**. On some phones it is under **Software information**.
2. Tap **Build number** seven times, until the phone says you are a developer.

## 2. Enable the Bluetooth log

1. Go to **Settings > System > Developer options**.
2. Turn on **Enable Bluetooth HCI snoop log**. If there are options, choose **Enabled** or **Full**.
3. Turn Bluetooth off and on again so the log starts fresh.

## 3. Record the actions

1. Open EDIFIER ConneX and connect to the speaker.
2. Do each action slowly, about 5 seconds apart, and write down the time of each one. For example: switch to each input, step the volume up and down, pick each EQ preset.
3. Close the app.

## 4. Get the log

1. In **Developer options**, tap **Take bug report** and choose **Interactive report**.
2. When it is ready, a notification appears. Send the `.zip` to your computer.
3. Inside the zip, the log is at `FS/data/misc/bluetooth/logs/btsnoop_hci.log` or a similar path.
4. Turn off **Enable Bluetooth HCI snoop log**.

## Privacy

A full bug report contains a lot of personal data. **Do not upload the `.zip` anywhere.** Extract only `btsnoop_hci.log`. That file also contains the Bluetooth addresses of your devices, so do not publish it as is either.

## Reading the log

Open `btsnoop_hci.log` in Wireshark and filter with `btatt`. Look for writes to characteristic `48090002-...` and notifications from `48090001-...`. Frames start with `AA EC` (requests) or `BB EC` (replies); the third byte is the opcode.
