#!/usr/bin/python

import socket
import numpy as np
import sys

# Настройки
UDP_PORT = 8080
WIDTH = 120
HEIGHT = 30

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("", UDP_PORT)) # Слушаем всех на этом порту
sock.settimeout(0.5)

print("Осциллограф запущен. Жду UDP пакеты...")

while True:
    try:
        data_raw, addr = sock.recvfrom(2048)
        # Кадр уже выровнен триггером на ESP32!
        view = np.frombuffer(data_raw, dtype=np.uint16)[:WIDTH]
        
        # Отрисовка (сетка + тонкая линия)
        frame = ["\033[H"]
        for y in range(HEIGHT, -1, -1):
            line = ""
            level = y * (4096 // HEIGHT)
            next_level = (y + 1) * (4096 // HEIGHT)
            for x, val in enumerate(view):
                is_signal = level <= val < next_level
                is_grid = (x % 10 == 0) or (y % 4 == 0)
                if is_signal: line += "█"
                elif is_grid: line += "·"
                else: line += " "
            frame.append(line)
            
        sys.stdout.write("\n".join(frame) + "\n")
        sys.stdout.flush()

    except socket.timeout:
        continue
