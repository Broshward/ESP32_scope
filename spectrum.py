#!/bin/python

import socket
import numpy as np
import sys
import threading
import time

# --- НАСТРОЙКИ ---
ESP32_IP = "192.168.1.51"
UDP_PORT = 8080
WIDTH = 120    # Ширина терминала
HEIGHT = 30    # Высота терминала
FS = 200000    # Частота дискретизации (Гц)
BUFFER_SIZE = 1024 # Размер буфера для FFT

# Состояния
spectrum_mode = "db" # "db" или "linear"
current_atten = 3
scale = 1
ATTEN_MAP = {0: 1.1, 1: 1.5, 2: 2.2, 3: 3.3}
avg_fft = None

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("", UDP_PORT))
sock.settimeout(0.5)

# --- ИНИЦИАЛИЗАЦИЯ ESP32 ---
def init_esp():
    print(f"Initializing ESP32 for Spectrum Analysis (Buffer: {BUFFER_SIZE})...")
    # Команды: Буфер, Триггер OFF, Scale 1, Частота
    cmds = [f"B {BUFFER_SIZE}", 
            "M 0", 
            f"S {scale}", 
            f"A {current_atten}", 
            f"F {FS}"]
    for c in cmds:
        sock.sendto(c.encode(), (ESP32_IP, UDP_PORT))
        time.sleep(0.1)

def draw_spectrum(data_raw):
    global FS, scale, spectrum_mode, HEIGHT, WIDTH, avg_fft
    
    # 1. Подготовка данных
    view = np.frombuffer(data_raw, dtype=np.uint16) & 0xFFF
    view = view.astype(np.float32)
    view -= np.mean(view) # Убираем постоянку (DC)

    # 2. FFT
    n = len(view)
    # Окно обязательно, чтобы не было "растекания" частот
    fft_res = np.abs(np.fft.rfft(view * np.hanning(n))) / (n / 2)
    
    # Убираем первые 2 бина (самый левый край), там всегда мусор
    fft_res[:2] = 1e-9

    if spectrum_mode == "db":
        if avg_fft is None or len(avg_fft) != len(fft_res):
            avg_fft = fft_res
        else:
            # Экспоненциальное сглаживание (90% старого, 10% нового)
            avg_fft = avg_fft * 0.9 + fft_res * 0.1
        # Логарифмическая шкала. Шум ESP обычно на -60..-70 дБ
        plot_data = 20 * np.log10(fft_res + 1e-9)
        y_min, y_max = 0, 80  # 0 дБ - это максимум (3.3В)
    else:
        # Линейная шкала (в вольтах)
        plot_data = fft_res * (3.3 / 4095.0)
        y_min, y_max = 0, 0.5 # Для начала возьмем 0.5В как максимум

    # 3. Создаем матрицу (заполняем пробелами)
    screen = [[" " for _ in range(WIDTH)] for _ in range(HEIGHT + 1)]
    
    # Рисуем сетку (точки)
    for y in range(HEIGHT + 1):
        for x in range(WIDTH):
            if x % 10 == 0 or y % 5 == 0: screen[y][x] = "·"

    # 4. Отрисовка столбиков
    # Растягиваем спектр на всю ширину WIDTH
    indices = np.linspace(0, len(plot_data) - 1, WIDTH).astype(int)
    
    for x, idx in enumerate(indices):
        val = plot_data[idx]
        
        # Считаем относительную высоту (от 0.0 до 1.0)
        ratio = (val - y_min) / (y_max - y_min)
        h = int(ratio * HEIGHT)
        
        # ОГРАНИЧЕНИЯ (чтобы не было белого экрана при зашкале)
        h = max(0, min(HEIGHT, h))
        
        # Рисуем столбик СНИЗУ ВВЕРХ
        # В терминале HEIGHT - это нижняя строка
        for y in range(HEIGHT - h, HEIGHT + 1):
            if 0 <= y <= HEIGHT:
                screen[y][x] = "█"

    # 5. Вывод
    eff_fs = FS / scale
    max_f = eff_fs / 2
    
    output = ["\033[H"] # Прыгаем в начало
    for row in screen:
        output.append("".join(row) + "\033[K")
    
    freq_labels = ""
    for i in range(6):
        f_val = (max_f * i / 5)
        freq_labels += f"{int(f_val):<20}" # Интервал между метками 0, 100, 200...
    output.append(f"\033[K{freq_labels}")

    # Инфо-строка
    status = f"Mode: {spectrum_mode.upper()} | Range: {int(max_f)} Hz | Max: {np.max(plot_data):.1f}"
    output.append(f"\033[K{status}")
    
    sys.stdout.write("\n".join(output))
    sys.stdout.flush()

def command_thread():
    global spectrum_mode, FS, scale
    sys.stdout.write(f"\033[{HEIGHT+5};1H\033[KCommand> ")
    while True:
        # Пустой input не перебивает наши координаты курсора
        cmd = sys.stdin.readline().strip() 
        if not cmd:
            sys.stdout.write("\033[%d;1H\033[KCommand> " %(HEIGHT+5))
            sys.stdout.flush()
            continue
            
        try:
            parts = cmd.split()
            if parts[0] == 's': # Скейл (время развертки)
                val = int(parts[1])
                scale = val
                sock.sendto(f"S{val}".encode(), (ESP32_IP, UDP_PORT))
            elif parts[0] == 'f': # Sampling frequency
                val = int(parts[1])
                FS = val
                sock.sendto(f"F{val}".encode(), (ESP32_IP, UDP_PORT))
            elif parts[0] == 'h':
                is_hold = not is_hold
            elif parts[0] == 'g': # Signal gain
                val = float(parts[1])
                v_gain = val
                sock.sendto(f"G{val}".encode(), (ESP32_IP, UDP_PORT))
            elif parts[0] == 'a':
                val = int(parts[1]) # 0 (1.1V), 1 (1.5V), 2 (2.2V), 3 (3.3V)
                current_atten = val
                sock.sendto(f"A{val}".encode(), (ESP32_IP, UDP_PORT))
            elif parts[0] == 'db':
                spectrum_mode = "db"
            elif parts[0] == 'lin': 
                spectrum_mode = "linear"
        except Exception as e:
            # Выводим ошибку на 29-ю строку, чтобы не ломать график
            sys.stdout.write(f"\033[%d;1H\033[KError: {e}" %(HEIGHT+5))
            
        # Очищаем строку ввода для следующей команды
        sys.stdout.write("\033[%d;1H\033[KCommand> " %(HEIGHT+5))
        sys.stdout.flush()
#    global spectrum_mode, FS
#    sys.stdout.write(f"\033[{HEIGHT+5};1H\033[KCommand> ")
#    sys.stdout.flush()
#    while True:
#        cmd = sys.stdin.readline().strip().lower()
#        if cmd == 'db':
#        elif cmd.startswith('f'): # Можно менять частоту и тут
#            FS = cmd.strip().split()[1]
#            sock.sendto(cmd.upper().encode(), (ESP32_IP, UDP_PORT))
#        sys.stdout.write(f"\033[{HEIGHT+5};1H\033[KCommand> ")
#        sys.stdout.flush()

# Запуск
init_esp()
threading.Thread(target=command_thread, daemon=True).start()
sys.stdout.write("\033[2J") # Очистка экрана

while True:
    try:
        data, addr = sock.recvfrom(4096)
        draw_spectrum(data)
    except Exception:
        continue
