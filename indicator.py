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
    print("[Ошибка] Не найдена библиотека индикатора.")
    exit(1)

from gi.repository import Gtk, GLib

class SensorsIndicator:
    def __init__(self):
        # Режим отображения: 'normal' или 'compact'
        self.mode = 'normal'

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
        self.sensors_menu_item = Gtk.MenuItem(label="Загрузка данных...")
        self.sensors_menu_item.set_sensitive(False)
        self.menu.append(self.sensors_menu_item)
        self.menu.append(Gtk.SeparatorMenuItem())
        
        # 2. Пункты переключения режимов
        # Создаем первую радио-кнопку
        self.mode_normal_item = Gtk.RadioMenuItem(label="Температура и вентилятор")
        self.mode_normal_item.set_active(True)
        self.mode_normal_item.connect("activate", self.on_mode_changed, 'normal')
        self.menu.append(self.mode_normal_item)
        
        # Создаем вторую радио-кнопку в той же группе
        self.mode_compact_item = Gtk.RadioMenuItem.new_with_label_from_widget(
            self.mode_normal_item, "Максимальная температура"
        )
        self.mode_compact_item.connect("activate", self.on_mode_changed, 'compact')
        self.menu.append(self.mode_compact_item)
        self.menu.append(Gtk.SeparatorMenuItem())
        
        # 3. Кнопка выхода
        quit_item = Gtk.MenuItem(label="Выход")
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
        """ Генерирует PNG-картинку в зависимости от выбранного режима """
        width, height = 55, 28
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

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
            max_temp_text = f"{max_temp}°" if max_temp > 0 else "N/A"
            
            # Загружаем крупный шрифт для одной цифры
            try:
                font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
            except IOError:
                font_large = ImageFont.load_default()
                
            color = self.get_color_for_temp(max_temp_text)
            
            # Центрируем текст по вертикали и горизонтали на холсте 55x28
            # (Отступы 14 и 4 подобраны для красивого выравнивания двухзначного числа)
            draw.text((14, 4), max_temp_text, font=font_large, fill=color)

        else:
            # ОБЫЧНЫЙ РЕЖИМ (Две строки: GPU/WiFi и Кулер)
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)
            except IOError:
                font = ImageFont.load_default()

            gpu_color = self.get_color_for_temp(gpu_text)
            wifi_color = self.get_color_for_temp(wifi_text)
            fan_color = self.get_color_for_fan(fan_text)

            # Рисуем "GPU/WiFi" с независимыми цветами
            draw.text((2, 0), gpu_text, font=font, fill=gpu_color)
            gpu_width = draw.textlength(gpu_text, font=font) if hasattr(draw, 'textlength') else 18
            
            draw.text((2 + gpu_width, 0), "/", font=font, fill=(255, 255, 255, 255))
            sep_width = draw.textlength("/", font=font) if hasattr(draw, 'textlength') else 6
            
            draw.text((2 + gpu_width + sep_width, 0), wifi_text, font=font, fill=wifi_color)

            # Рисуем кулер
            draw.text((2, 13), f"{fan_text}", font=font, fill=fan_color)

        image.save(path, "PNG")

    def get_sensors_output(self):
        try:
            result = subprocess.run(['sensors'], capture_output=True, text=True, check=True)
            return result.stdout
        except Exception as e:
            return f"Ошибка получения данных: {e}"

    def parse_temperatures(self, text):
        gpu_temp = "N/A"
        wifi_temp = "N/A"
        fan_speed = "N/A"
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
