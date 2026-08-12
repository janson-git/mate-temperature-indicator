#!/usr/bin/env python3
import re
import subprocess
import os
import gi
from PIL import Image, ImageDraw, ImageFont

gi.require_version('Gtk', '3.0')

# Prefer Ayatana, fall back to classic AppIndicator
indicator_loaded = False
for ns in ['AyatanaAppIndicator3', 'AyatanaAppindicator3', 'AppIndicator3']:
    try:
        gi.require_version(ns, '0.1')
        AppIndicator = __import__(f'gi.repository.{ns}', fromlist=[ns])
        indicator_loaded = True
        break
    except (ValueError, ImportError):
        continue

if not indicator_loaded:
    print("[Error] Indicator library not found.")
    exit(1)

from gi.repository import Gtk, GLib

#FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
#FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf"
FONT_PATH = "/usr/share/fonts/truetype/ubuntu/Ubuntu-M.ttf"
DEFAULT_PANEL_SIZE = 32
FAN_PROC_PATH = "/proc/acpi/ibm/fan"


class SensorsIndicator:
    def __init__(self):
        # Display mode: 'normal' or 'compact'
        self.mode = 'normal'
        self.icon_size = self.get_icon_canvas_size()

        # Initialize indicator with a temporary placeholder icon
        self.indicator = AppIndicator.Indicator.new(
            "sensors_tray_indicator",
            "/tmp/sensors_tray_icon_init.png",
            AppIndicator.IndicatorCategory.APPLICATION_STATUS
        )
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)

        # Build menu
        self.menu = Gtk.Menu()
        
        # 1. Full sensors dump (non-clickable)
        self.sensors_menu_item = Gtk.MenuItem(label="Loading data...")
        self.sensors_menu_item.set_sensitive(False)
        self.menu.append(self.sensors_menu_item)
        self.menu.append(Gtk.SeparatorMenuItem())
        
        # 2. Display mode radio items
        # First radio button
        self.mode_normal_item = Gtk.RadioMenuItem(label="Temperature and fan")
        self.mode_normal_item.set_active(True)
        self.mode_normal_item.connect("activate", self.on_mode_changed, 'normal')
        self.menu.append(self.mode_normal_item)
        
        # Second radio button in the same group
        self.mode_compact_item = Gtk.RadioMenuItem.new_with_label_from_widget(
            self.mode_normal_item, "Maximum temperature"
        )
        self.mode_compact_item.connect("activate", self.on_mode_changed, 'compact')
        self.menu.append(self.mode_compact_item)
        self.menu.append(Gtk.SeparatorMenuItem())

        # 3. Fan control (submenu)
        fan_root = Gtk.MenuItem(label="Set fan speed")
        fan_sub = Gtk.Menu()
        fan_auto_item = Gtk.MenuItem(label="Auto")
        fan_auto_item.connect("activate", self.on_fan_auto)
        fan_sub.append(fan_auto_item)
        fan_full_item = Gtk.MenuItem(label="Full speed (2 min)")
        fan_full_item.connect("activate", self.on_fan_full_speed)
        fan_sub.append(fan_full_item)
        fan_root.set_submenu(fan_sub)
        if not os.path.exists(FAN_PROC_PATH):
            fan_root.set_sensitive(False)
        self.menu.append(fan_root)
        self.menu.append(Gtk.SeparatorMenuItem())
        
        # 4. Quit
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", Gtk.main_quit)
        self.menu.append(quit_item)
        
        self.menu.show_all()
        self.indicator.set_menu(self.menu)

        # First refresh
        self.update_data()

        # Refresh every 3 seconds
        GLib.timeout_add(3000, self.update_data)

    def on_mode_changed(self, widget, mode_name):
        """Handle display mode radio button clicks."""
        if widget.get_active():
            self.mode = mode_name
            self.update_data()  # Refresh icon immediately on mode switch

    def on_fan_auto(self, _widget):
        self.write_fan_commands(["level auto"])

    def on_fan_full_speed(self, _widget):
        self.write_fan_commands(["level full-speed", "watchdog 120"])

    def show_error(self, message):
        dialog = Gtk.MessageDialog(
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=message,
        )
        dialog.set_title("Fan control")
        dialog.run()
        dialog.destroy()

    def write_fan_commands(self, commands):
        """Write commands to the thinkpad fan proc via pkexec (one auth prompt per action)."""
        if not os.path.exists(FAN_PROC_PATH):
            self.show_error(f"Fan control interface not found:\n{FAN_PROC_PATH}")
            return False

        # Commands come only from our code; still escape for the shell
        parts = []
        for command in commands:
            safe = command.replace("'", "'\\''")
            parts.append(f"printf '%s\\n' '{safe}' > '{FAN_PROC_PATH}'")
        script = " && ".join(parts)

        try:
            result = subprocess.run(
                ["pkexec", "sh", "-c", script],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            self.show_error("pkexec not found. Install policykit-1.")
            return False
        except Exception as e:
            self.show_error(f"Failed to run pkexec:\n{e}")
            return False

        if result.returncode != 0:
            # User cancelled the auth dialog — stay quiet
            stderr = (result.stderr or "").strip()
            if result.returncode in (126, 127) and not stderr:
                return False
            detail = stderr or f"exit code {result.returncode}"
            self.show_error(f"Could not set fan mode:\n{detail}")
            return False

        return True

    def get_panel_size(self):
        """Read MATE panel height; the tray forces icons into a square slot."""
        try:
            listed = subprocess.run(
                ['dconf', 'list', '/org/mate/panel/toplevels/'],
                capture_output=True, text=True, check=True
            ).stdout.splitlines()
            for entry in listed:
                name = entry.strip().strip('/')
                if not name:
                    continue
                result = subprocess.run(
                    ['dconf', 'read', f'/org/mate/panel/toplevels/{name}/size'],
                    capture_output=True, text=True, check=False
                )
                value = result.stdout.strip()
                if value.isdigit():
                    return max(16, int(value))
        except Exception:
            pass
        return DEFAULT_PANEL_SIZE

    def get_icon_canvas_size(self):
        """Square canvas (>= panel size) so the tray does not squash a wide PNG."""
        panel = self.get_panel_size()
        # 2x gives sharper text after the panel downscales to the slot height
        return max(panel * 2, 64)

    def load_font(self, size):
        try:
            return ImageFont.truetype(FONT_PATH, size)
        except OSError:
            return ImageFont.load_default()

    def text_bbox(self, text, font):
        left, top, right, bottom = font.getbbox(text)
        return left, top, right - left, bottom - top

    def text_size(self, text, font):
        _, _, width, height = self.text_bbox(text, font)
        return width, height

    def draw_text(self, draw, xy, text, font, fill, anchor="lt"):
        """Draw text using font ink bbox (anchor: lt / lm / mm)."""
        x, y = xy
        left, top, width, height = self.text_bbox(text, font)
        if anchor == "mm":
            x -= width / 2
            y -= height / 2
        elif anchor == "lm":
            y -= height / 2
        draw.text((x - left, y - top), text, font=font, fill=fill)

    def largest_font(self, texts, max_size, pad=4, gap=2):
        """Pick the largest font size that fits all lines in the square canvas."""
        size = self.icon_size
        for font_size in range(max_size, 6, -1):
            font = self.load_font(font_size)
            widths = []
            heights = []
            for text in texts:
                w, h = self.text_size(text, font)
                widths.append(w)
                heights.append(h)
            total_h = sum(heights) + gap * (len(texts) - 1)
            if max(widths) <= size - 2 * pad and total_h <= size - 2 * pad:
                return font, heights
        font = self.load_font(7)
        return font, [self.text_size(t, font)[1] for t in texts]

    def get_color_for_temp(self, temp_str):
        """Return RGBA color based on temperature."""
        try:
            val = int(re.sub(r'[^\d.]', '', temp_str))
            if val >= 70:
                return (255, 0, 0, 255)    # Red
            elif val >= 60:
                return (255, 255, 0, 255)  # Yellow
        except ValueError:
            pass
        return (255, 255, 255, 255)        # White

    def get_color_for_fan(self, fan_str):
        """Return RGBA color based on fan RPM."""
        try:
            val = int(fan_str)
            if val >= 5500:
                return (255, 0, 0, 255)    # Red
            elif val >= 4000:
                return (255, 255, 0, 255)  # Yellow
        except ValueError:
            pass
        return (255, 255, 255, 255)        # White

    def create_image_icon(self, gpu_text, wifi_text, fan_text, path):
        """Generate a square PNG sized for the tray icon slot."""
        size = self.icon_size
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        cx = size / 2

        if self.mode == 'compact':
            # Compact mode: show the maximum of the two temperatures
            try:
                gpu_val = int(re.sub(r'[^\d.]', '', gpu_text))
            except ValueError:
                gpu_val = 0
            try:
                wifi_val = int(re.sub(r'[^\d.]', '', wifi_text))
            except ValueError:
                wifi_val = 0
            
            max_temp = max(gpu_val, wifi_val)
            max_temp_text = f"{max_temp}°" if max_temp > 0 else "--"
            font, _ = self.largest_font([max_temp_text], max_size=size - 8)
            color = self.get_color_for_temp(max_temp_text)
            self.draw_text(draw, (cx, size / 2), max_temp_text, font, color, anchor="mm")

        else:
            # Normal mode (two lines: GPU/WiFi and fan)
            line1 = f"{gpu_text}/{wifi_text}"
            line2 = str(fan_text)
            font, heights = self.largest_font([line1, line2], max_size=size // 2)
            gap = 2
            block_h = heights[0] + gap + heights[1]
            y1 = (size - block_h) / 2 + heights[0] / 2
            y2 = y1 + heights[0] / 2 + gap + heights[1] / 2

            gpu_color = self.get_color_for_temp(gpu_text)
            wifi_color = self.get_color_for_temp(wifi_text)
            fan_color = self.get_color_for_fan(fan_text)

            # Temperature line with independent colors, aligned as one block
            gpu_w = self.text_size(gpu_text, font)[0]
            sep_w = self.text_size("/", font)[0]
            wifi_w = self.text_size(wifi_text, font)[0]
            line1_w = gpu_w + sep_w + wifi_w
            x = (size - line1_w) / 2
            self.draw_text(draw, (x, y1), gpu_text, font, gpu_color, anchor="lm")
            x += gpu_w
            self.draw_text(draw, (x, y1), "/", font, (255, 255, 255, 255), anchor="lm")
            x += sep_w
            self.draw_text(draw, (x, y1), wifi_text, font, wifi_color, anchor="lm")

            self.draw_text(draw, (cx, y2), line2, font, fan_color, anchor="mm")

        image.save(path, "PNG")

    def get_sensors_output(self):
        try:
            result = subprocess.run(['sensors'], capture_output=True, text=True, check=True)
            return result.stdout
        except Exception as e:
            return f"Error fetching data: {e}"

    def parse_temperatures(self, text):
        gpu_temp = "--"
        wifi_temp = "--"
        fan_speed = "--"
        blocks = text.split('\n\n')
        
        for block in blocks:
            if "iwlwifi_1-virtual-0" in block:
                wifi_match = re.search(r'temp1:\s+\+?([\d.]+)', block)
                if wifi_match:
                    wifi_temp = f"{int(float(wifi_match.group(1)))}°"
            
            if "thinkpad-isa-0000" in block:
                gpu_match = re.search(r'GPU:\s+\+?([\d.]+)', block)
                if gpu_match:
                    gpu_temp = f"{int(float(gpu_match.group(1)))}°"

                fan_match = re.search(r'fan1:\s+(\d+)\s+RPM', block)
                if fan_match:
                    fan_speed = fan_match.group(1)

        return gpu_temp, wifi_temp, fan_speed

    def format_tooltip(self, gpu_text, wifi_text, fan_text):
        """Tooltip always shows both temperatures and fan, regardless of display mode."""
        fan_label = fan_text if fan_text == "--" else f"{fan_text} RPM"
        return f"GPU: {gpu_text}\nWiFi: {wifi_text}\nFan: {fan_label}"

    def update_data(self):
        import time
        full_output = self.get_sensors_output()
        gpu, wifi, fan = self.parse_temperatures(full_output)

        # Unique path to bypass panel icon caching
        current_icon_path = f"/tmp/sensors_tray_icon_{int(time.time() * 1000)}.png"

        # Create icon (create_image_icon checks self.mode)
        self.create_image_icon(gpu, wifi, fan, current_icon_path)
        
        # Force-refresh the tray icon
        self.indicator.set_icon_full(current_icon_path, "sensors_icon")
        self.indicator.set_title(self.format_tooltip(gpu, wifi, fan))

        # Update sensors dump in the menu
        self.sensors_menu_item.set_label(full_output.strip())

        # Remove old temporary icon files
        try:
            for file in os.listdir("/tmp"):
                if file.startswith("sensors_tray_icon_") and file.endswith(".png"):
                    full_file_path = os.path.join("/tmp", file)
                    if full_file_path != current_icon_path:
                        os.remove(full_file_path)
        except Exception:
            pass

        return True

if __name__ == "__main__":
    app = SensorsIndicator()
    Gtk.main()
