#!/usr/bin/python

import socket
import numpy as np
import sys
import threading
import termios,tty

# Настройки
ESP32_IP = "192.168.1.51"
UDP_PORT = 8080
WIDTH = 128
HEIGHT = 30
line_mode = 1           # Points connected with lines
clipping = True         # Clipping ( Delete points 0..16, 4080..4095 )
is_hold = 0             # Hold screen

v_threshold = 2000      # Vertical threshold(voltage threshold)
sample_freq = 2000000   # Sample frequency
t_scale = 1             # Time scale
tr_state = 0            # Trigger state (on/off)
tr_edge = 1             # Edge rising/falling
v_gain = 1              # Voltage gain (Vertical scale)
current_atten = 3       # Аттенюатор АЦП (3 - 3.3V max)
current_offset = 0      # Voltage offset


ATTEN_MAP = {
    0: 1.1,  # ADC_ATTEN_DB_0
    1: 1.5,  # ADC_ATTEN_DB_2_5
    2: 2.2,  # ADC_ATTEN_DB_6
    3: 3.3   # ADC_ATTEN_DB_12
}

def get_voltage_stats(view, atten_idx):
    max_v_range = ATTEN_MAP.get(atten_idx, 3.3)
    
    # Превращаем беззнаковый uint16 в знаковый float или int32
    # Это позволит нам уходить в минус без ошибок Overflow
    view_safe = view.astype(np.float32) 
        
    # Пересчитываем массив "попугаев" (0-4095) в Вольты
    # Сначала убираем смещение и возвращаем масштаб, потом переводим в вольты
    raw_corrected = ((view_safe - current_offset - v_threshold ) / v_gain) + v_threshold
    voltages = raw_corrected * (max_v_range / 4095.0) / v_gain
    
    voltages = view * (max_v_range / 4095.0) / v_gain
    
    v_min = np.min(voltages)
    v_max = np.max(voltages)
    v_pp = v_max - v_min # Peak-to-Peak (размах)
    v_avg = np.mean(voltages) # Среднее (DC составляющая)

    #RMS
    # Вычитаем постоянную составляющую (DC), чтобы мерить только AC RMS
    ac_component = voltages - v_avg
    rms = np.sqrt(np.mean(ac_component**2))
    
    return v_min, v_max, v_pp, v_avg, rms

def get_v_div(atten_idx, height):
    max_v = ATTEN_MAP.get(atten_idx, 3.3)
    v_per_div = (max_v / height) * 4 / v_gain
    
    if v_per_div < 0.1:
        return f"{v_per_div * 1000:.1f} mV/div"
    return f"{v_per_div:.2f} V/div"

def calculate_frequency(view, fs, scale):
    # Находим все индексы, где сигнал пересекает порог (v_threshold) вверх
    # (data < v_threshold) дает массив True/False, np.diff находит смену состояния
    crossings = np.where((view[:-1] < v_threshold) & (view[1:] >= v_threshold))[0]
    
    if len(crossings) >= 2:
        # Расстояние между двумя соседними пересечениями (период в точках)
        # Берем среднее между всеми найденными периодами для точности
        period_samples = np.mean(np.diff(crossings))
        
        # Реальная частота с учетом децимации (scale)
        if period_samples > 0:
            freq = fs / (period_samples * scale) 
        else:
            freq = 0
    else:
        freq = 0

    if freq > 1000:
        freq_str = f"{freq/1000:.2f} kHz"
    else:
        freq_str = f"{freq:.1f} Hz"
    return freq_str

def get_time_div():
    # Время одного деления в секундах
    time_per_div = (t_scale / sample_freq) * 10
    
    # Красивое форматирование (мс или мкс)
    if time_per_div < 0.001:
        return f"{time_per_div * 1000000:.1f} us/div"
    elif time_per_div < 1:
        return f"{time_per_div * 1000:.1f} ms/div"
    else:
        return f"{time_per_div:.2f} s/div"

def command_thread():
    global v_threshold, sample_freq, t_scale, tr_state, is_hold, v_gain, current_atten, current_offset, line_mode, clipping, tr_edge
    # Печатаем приглашение один раз в самом низу
    sys.stdout.write(f"\033[{HEIGHT+5};1H\033[KCommand> ")
    #sys.stdout.flush()
    
    while True:
        # Пустой input не перебивает наши координаты курсора
        cmd = sys.stdin.readline().strip() 
        if not cmd:
            sys.stdout.write("\033[%d;1H\033[KCommand> " %(HEIGHT+5))
            sys.stdout.flush()
            continue
            
        try:
            parts = cmd.split()
            if parts[0] == 't': # Порог
                val = int(parts[1])
                v_threshold = val
                sock.sendto(f"T{val}".encode(), (ESP32_IP, UDP_PORT))
            elif parts[0] == 's': # Скейл (время развертки)
                val = int(parts[1])
                t_scale = val
                sock.sendto(f"S{val}".encode(), (ESP32_IP, UDP_PORT))
            elif parts[0] == 'f': # Sampling frequency
                val = int(parts[1])
                sample_freq = val
                sock.sendto(f"F{val}".encode(), (ESP32_IP, UDP_PORT))
            elif parts[0] == 'm': # Trigger on/off
                tr_state = 0 if tr_state==1 else 1
                sock.sendto(f"M{tr_state}".encode(), (ESP32_IP, UDP_PORT))
            elif parts[0] == 'e': # Trigger edge (rising/falling)
                tr_edge = 0 if tr_edge==1 else 1
                sock.sendto(f"E{tr_edge}".encode(), (ESP32_IP, UDP_PORT))
            elif parts[0] == 'h':
                is_hold = not is_hold
            elif parts[0] == 'l':
                line_mode = not line_mode
            elif parts[0] == 'k':
                clipping = not clipping
            elif parts[0] == 'g': # Signal gain
                val = float(parts[1])
                v_gain = val
                sock.sendto(f"G{val}".encode(), (ESP32_IP, UDP_PORT))
            elif parts[0] == 'a':
                val = int(parts[1]) # 0 (1.1V), 1 (1.5V), 2 (2.2V), 3 (3.3V)
                current_atten = val
                sock.sendto(f"A{val}".encode(), (ESP32_IP, UDP_PORT))
            elif parts[0] == 'o': # Signal gain
                val = int(parts[1])
                current_offset = val
                sock.sendto(f"o{val}".encode(), (ESP32_IP, UDP_PORT))
            #elif parts[0] == 'q': 
            #    exit(0)
        except Exception as e:
            # Выводим ошибку на 29-ю строку, чтобы не ломать график
            sys.stdout.write(f"\033[%d;1H\033[KError: {e}" %(HEIGHT+2))
            
        # Очищаем строку ввода для следующей команды
        sys.stdout.write("\033[%d;1H\033[KCommand> " %(HEIGHT+5))
        sys.stdout.flush()

threading.Thread(target=command_thread, daemon=True).start()

def draw_plot(view):
    # Создаем матрицу (размер точно HEIGHT+1 на WIDTH)
    screen = [[" " for _ in range(WIDTH)] for _ in range(HEIGHT + 1)]

    # Сетка
    for y in range(HEIGHT + 1):
        for x in range(WIDTH):
            if x % 10 == 0 or y % 4 == 0:
                screen[y][x] = "·"

    # РИСОВАНИЕ
    prev_y = None
    # Ограничиваем цикл ровно по ширине WIDTH
    for x in range(min(len(view), WIDTH)):
        val = view[x]
        
        # Клиппинг
        if clipping:
            if val < 16 or val > 4080:
                prev_y = None
                continue

        # ПРАВИЛЬНЫЙ РАСЧЕТ ИНДЕКСА СТРОКИ:
        # 0.0 ... 1.0 (процент заполнения)
        ratio = val / 4095.0
        # Индекс строки: 0 - верх, HEIGHT - низ
        # 4095 -> 0, 0 -> HEIGHT
        current_y = int(HEIGHT - (ratio * HEIGHT))
        
        # Защита от вылета
        current_y = max(0, min(HEIGHT, current_y))

        if line_mode and prev_y is not None:
            y_min = min(prev_y, current_y)
            y_max = max(prev_y, current_y)
            for y in range(y_min, y_max + 1):
                screen[y][x] = "█"
        else:
            screen[current_y][x] = "█"
        
        prev_y = current_y

    # ВЫВОД (печать ровно HEIGHT строк)
    output = ["\033[s\033[H"]
    for row_idx in range(HEIGHT + 1):
        output.append("".join(screen[row_idx]) + "\033[K")
    # Вывод
    sys.stdout.write("\n".join(output) + "\n")

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("", UDP_PORT)) # Слушаем всех на этом порту
sock.settimeout(0.5)
#print("Осциллограф запущен. Жду UDP пакеты...")

hold_flag=0
while True:
    try:
        data_raw, addr = sock.recvfrom(2048)
        view = np.frombuffer(data_raw, dtype=np.uint16)[:WIDTH]
        # Сначала ПРОВЕРЯЕМ, что пришло. 
        # Если в view есть значения > 4095, значит данные битые
        view = np.clip(view, 0, 4095) 


        if is_hold:
            sys.stdout.write('\033[s \033[0;0f THE SCREEN is HOLDED! Enter the "h" command!\033[u')   
            sys.stdout.flush()
            hold_flag=1
            continue # Просто игнорируем новые данные, старый график остается на экране
        else:
            if hold_flag==1:
                sys.stdout.write('\033[s\033[0;0f\033[2K\033[u')
                hold_flag=0

        
        # Frequency calc
        freq = calculate_frequency(view, sample_freq, t_scale)
        
        # Voltage calc
        v_min, v_max, v_pp, v_avg, v_rms = get_voltage_stats(view, current_atten)
        v_div_str = get_v_div(current_atten, HEIGHT)

        # Рисуем осциллограмму      
        draw_plot(view)
        
        # Выводим информацию
        sys.stdout.write(f"Trigger Threshold(t): {v_threshold} | Sampling freq(f): {sample_freq} | Time scale(s): {t_scale} | Trigger(m) {"off" if tr_state==0 else "on"}, {'rising' if tr_edge else 'falling'} | {get_time_div()} | {freq}\033[K\n")
        sys.stdout.write(f"Vpp: {v_pp:.3f}V | Vmin: {v_min:.3f} | Vmax: {v_max:.3f}V | Vavg: {v_avg:.3f}V | Vrms: {v_rms:.3f}V | {v_div_str} | Offset(o): {current_offset} | Gain(g): {v_gain:.1f}\033[K")
        
        sys.stdout.write("\033[u")
        sys.stdout.flush()

    except socket.timeout:
        continue

