#!/usr/bin/env python3
import re
import subprocess
import os
import gi
from PIL import Image, ImageDraw, ImageFont

gi.require_version('Gtk', '3.0')

# Умный импорт библиотек индикатора
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
        # Режим отображения: 'normal' или 'compact'
        self.mode = 'normal'
        self.icon_size = self.get_icon_canvas_size()

        # Инициализируем индикатор с временной заглушкой
        self.indicator = AppIndicator.Indicator.new(
            "sensors_tray_indicator",
            "/tmp/sensors_tray_icon_init.png",
            AppIndicator.IndicatorCategory.APPLICATION_STATUS
        )
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)

        # Создаем меню
        self.menu = Gtk.Menu()
        
        # 1. Элемент меню для вывода всех сенсоров (некликабельный)
        self.sensors_menu_item = Gtk.MenuItem(label="Loading data...")
        self.sensors_menu_item.set_sensitive(False)
        self.menu.append(self.sensors_menu_item)
        self.menu.append(Gtk.SeparatorMenuItem())
        
        # 2. Пункты переключения режимов
        # Создаем первую радио-кнопку
        self.mode_normal_item = Gtk.RadioMenuItem(label="Temperature and fan")
        self.mode_normal_item.set_active(True)
        self.mode_normal_item.connect("activate", self.on_mode_changed, 'normal')
        self.menu.append(self.mode_normal_item)
        
        # Создаем вторую радио-кнопку в той же группе
        self.mode_compact_item = Gtk.RadioMenuItem.new_with_label_from_widget(
            self.mode_normal_item, "Maximum temperature"
        )
        self.mode_compact_item.connect("activate", self.on_mode_changed, 'compact')
        self.menu.append(self.mode_compact_item)
        self.menu.append(Gtk.SeparatorMenuItem())

        # 3. Управление вентилятором (submenu)
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
        
        # 4. Кнопка выхода
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", Gtk.main_quit)
        self.menu.append(quit_item)
        
        self.menu.show_all()
        self.indicator.set_menu(self.menu)

        # Первое обновление
        self.update_data()

        # Таймер обновления на 3 секунды
        GLib.timeout_add(3000, self.update_data)

    def on_mode_changed(self, widget, mode_name):
        """ Срабатывает при клике на радио-кнопки переключения режимов """
        if widget.get_active():
            self.mode = mode_name
            self.update_data() # Мгновенно обновляем иконку при переключении

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
        """ Пишет команды в thinkpad fan proc через pkexec (один запрос на действие). """
        if not os.path.exists(FAN_PROC_PATH):
            self.show_error(f"Fan control interface not found:\n{FAN_PROC_PATH}")
            return False

        # Только доверенные строки из нашего кода — экранируем на всякий случай
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
            # Пользователь отменил диалог авторизации — без шумного окна
            stderr = (result.stderr or "").strip()
            if result.returncode in (126, 127) and not stderr:
                return False
            detail = stderr or f"exit code {result.returncode}"
            self.show_error(f"Could not set fan mode:\n{detail}")
            return False

        return True

    def get_panel_size(self):
        """ Читает высоту панели MATE; трей принудительно вписывает иконки в квадрат. """
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
        """ Квадратный холст (≥ панели), чтобы трей не сжимал широкий PNG. """
        panel = self.get_panel_size()
        # 2× даёт более чёткий текст после даунскейла панелью до высоты слота
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
        """ Рисует текст с учётом ink-bbox шрифта (якорь: lt / lm / mm). """
        x, y = xy
        left, top, width, height = self.text_bbox(text, font)
        if anchor == "mm":
            x -= width / 2
            y -= height / 2
        elif anchor == "lm":
            y -= height / 2
        draw.text((x - left, y - top), text, font=font, fill=fill)

    def largest_font(self, texts, max_size, pad=4, gap=2):
        """ Подбирает максимальный кегль, при котором все строки помещаются в квадрат. """
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
        """ Возвращает RGB цвет в зависимости от температуры """
        try:
            val = int(re.sub(r'[^\d.]', '', temp_str))
            if val >= 70:
                return (255, 0, 0, 255)    # Красный
            elif val >= 60:
                return (255, 255, 0, 255)  # Жёлтый
        except ValueError:
            pass
        return (255, 255, 255, 255)        # Белый

    def get_color_for_fan(self, fan_str):
        """ Возвращает RGB цвет в зависимости от оборотов вентилятора """
        try:
            val = int(fan_str)
            if val >= 5500:
                return (255, 0, 0, 255)    # Красный
            elif val >= 4000:
                return (255, 255, 0, 255)  # Жёлтый
        except ValueError:
            pass
        return (255, 255, 255, 255)        # Белый

    def create_image_icon(self, gpu_text, wifi_text, fan_text, path):
        """ Генерирует квадратный PNG под размер слота трея """
        size = self.icon_size
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        cx = size / 2

        if self.mode == 'compact':
            # КОМПАКТНЫЙ РЕЖИМ: Выбираем максимальную температуру
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
            # ОБЫЧНЫЙ РЕЖИМ (Две строки: GPU/WiFi и Кулер)
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

            # Строка температур с независимыми цветами, выровненная как один блок
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
        """ Tooltip всегда показывает обе температуры и вентилятор, независимо от режима. """
        fan_label = fan_text if fan_text == "--" else f"{fan_text} RPM"
        return f"GPU: {gpu_text}\nWiFi: {wifi_text}\nFan: {fan_label}"

    def update_data(self):
        import time
        full_output = self.get_sensors_output()
        gpu, wifi, fan = self.parse_temperatures(full_output)

        # Генерируем уникальный путь к файлу для обхода кэша панели
        current_icon_path = f"/tmp/sensors_tray_icon_{int(time.time() * 1000)}.png"

        # Создаем иконку (логика внутри create_image_icon сама проверит self.mode)
        self.create_image_icon(gpu, wifi, fan, current_icon_path)
        
        # Принудительно обновляем иконку в системном трее
        self.indicator.set_icon_full(current_icon_path, "sensors_icon")
        self.indicator.set_title(self.format_tooltip(gpu, wifi, fan))

        # Обновляем лог в меню
        self.sensors_menu_item.set_label(full_output.strip())

        # Очищаем старые временные файлы иконок
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
