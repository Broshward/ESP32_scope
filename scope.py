#!/usr/bin/python

import socket
import numpy as np
import os
import sys

# Настройки
IP = "192.168.1.51"
PORT = 8080
WIDTH = 120
HEIGHT = 30

# Настройки триггера
THRESHOLD = 2048
WINDOW_SIZE = 5 # Сколько точек усредняем для проверки

def get_freq(data, sample_rate=100000):
    # Находим индексы всех пересечений порога вверх
    crossings = np.where((data[:-1] < 2048) & (data[1:] >= 2048))[0]
    if len(crossings) >= 2:
        period_samples = np.mean(np.diff(crossings)) # Среднее расстояние между пиками
        return sample_rate / period_samples
    return 0

def find_trigger(data, low=1900, high=2200):
    state = "low"
    for i in range(len(data) - WIDTH):
        if state == "low" and data[i] < low:
            state = "ready"
        if state == "ready" and data[i] > high:
            return i
    return len(data)

def get_fresh_data():
    """Вычитывает ВСЁ из сокета и возвращает только последний кусок"""
    final_data = b""
    while True:
        try:
            chunk = sock.recv(4096)
            if not chunk: break
            final_data = chunk # Оставляем только самое свежее
        except BlockingIOError:
            break
    return np.frombuffer(final_data, dtype=np.uint16) & 0xFFF if final_data else None

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((IP, PORT))
sock.setblocking(False)

while True:
    data = get_fresh_data()
    if data is None or len(data) < WIDTH + 20: 
        continue

#    start_index = find_trigger(data)
    start_index = 0
    view = data[start_index : start_index + WIDTH]

    # 2. СБОРКА КАДРА (Сетка + Линия)
    frame = ["\033[H"] # Курсор в начало (быстрее чем clear)
    for y in range(HEIGHT, -1, -1):
        line = ""
        level = y * (4096 // HEIGHT)
        next_level = (y + 1) * (4096 // HEIGHT)
        
        for x, val in enumerate(view):
            # Проверяем, попадает ли сигнал в текущую "строку"
            is_signal = level <= val < next_level
            is_grid = (x % 10 == 0) or (y % 4 == 0)

            if is_signal:
                line += "█"
            elif is_grid:
                line += "·"
            else:
                line += " "
        frame.append(line)
    
    # 3. ВЫВОД ОДНИМ МАХОМ
    sys.stdout.write("\n".join(frame) + "\n")
    sys.stdout.flush()
