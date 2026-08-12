# mate-temperature-indicator

Linux Mint MATE indicator to show temperature and fan speed on Lenovo Thinkpad P15s

<img width="85" height="44" alt="image" src="https://github.com/user-attachments/assets/28692513-5442-43a7-81c5-52652042e12c" />

<img width="124" height="119" alt="image" src="https://github.com/user-attachments/assets/1897ea3a-6ff7-44a6-b8f8-8e21953d1743" />

## Requirements

### Desktop / MATE version

| Item | Minimum | Notes |
|------|---------|--------|
| Desktop | **Linux Mint MATE** | Developed and tested on Mint MATE |
| MATE panel | **≥ 1.26** | Matches Linux Mint **21.3** and newer |
| Indicator host | **mate-indicator-applet** (or XApp Status applet that shows AppIndicators) | Tray icon is an Ayatana/AppIndicator, not a classic panel applet |

Tested on:

- Linux Mint **21.3** MATE
- Linux Mint **22.3** MATE

### System packages

```bash
sudo apt update
sudo apt install \
  python3 \
  python3-gi \
  python3-gi-cairo \
  gir1.2-gtk-3.0 \
  gir1.2-ayatanaappindicator3-0.1 \
  mate-indicator-applet \
  python3-pil \
  lm-sensors \
  policykit-1 \
  fonts-ubuntu
```

Optional / hardware-specific:

- **ThinkPad fan control** (`Set fan speed` menu): needs `/proc/acpi/ibm/fan` (kernel module `thinkpad_acpi`) and `pkexec` from `policykit-1`.
- If Ayatana is missing on an older system, `gir1.2-appindicator3-0.1` may work as a fallback (the script tries both).

### Panel setup

1. Right-click the MATE panel → **Add to Panel…**
2. Add **Indicator Applet** (or **Indicator Applet Complete**), if it is not already present.
3. Confirm the tray area is visible (clock / network / other indicators appear there).

## Install

1. Clone or copy the project somewhere permanent, for example:

```bash
mkdir -p ~/apps
cd ~/apps
git clone <repository-url> mate_temp_applet
# or copy the folder manually
```

2. Make the script executable:

```bash
chmod +x ~/apps/mate_temp_applet/indicator.py
```

3. Adjust the path below if you installed the project elsewhere.

## Run manually

```bash
python3 ~/apps/mate_temp_applet/indicator.py
```

Or:

```bash
~/apps/mate_temp_applet/indicator.py
```

The temperature / fan icon should appear in the indicator area of the panel.

Stop it:

Do right-click on applet and choose "Quit" option

Or run a command:

```bash
pkill -f 'mate_temp_applet/indicator.py'
```

(Use a path unique enough that you do not kill unrelated processes.)



## Autostart (MATE)

### Startup Applications (GUI)

1. Open **Menu → Preferences → Startup Applications** (or search for “Startup Applications”).
2. Click **Add**.
3. Fill in:
   - **Name:** `Temperature Indicator`
   - **Command:** `python3 /home/YOUR_USER/apps/mate_temp_applet/indicator.py`
   - **Comment:** optional
4. Save and log out / log in (or reboot).

Replace `YOUR_USER` and the path with your real install location.


## Fan control notes

Menu **Set fan speed**:

- **Auto** — writes `level auto` to `/proc/acpi/ibm/fan` via `pkexec`
- **Full speed (2 min)** — writes `level full-speed` and `watchdog 120` via one `pkexec` prompt

A PolicyKit password dialog will appear. If `/proc/acpi/ibm/fan` is missing, the fan menu item is disabled.

## Troubleshooting

| Symptom | What to check |
|---------|----------------|
| `[Error] Indicator library not found.` | Install `gir1.2-ayatanaappindicator3-0.1` (or AppIndicator3) |
| Script runs but no icon | Add **Indicator Applet** to the panel; ensure only one copy of the script is running |
| Temps show `--` | Run `sensors` in a terminal; sensor chip names may differ from this ThinkPad setup |
| Fan menu greyed out | No `/proc/acpi/ibm/fan` — load/enable `thinkpad_acpi` if appropriate for your machine |
| `pkexec` fails | Install `policykit-1`; confirm a graphical session is active |
