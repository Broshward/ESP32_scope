#!/usr/bin/python

import socket
import numpy as np
import sys
import threading
import termios,tty

# Настройки
ESP32_IP = "192.168.1.51"
threshold = 2000
UDP_PORT = 8080
WIDTH = 120
HEIGHT = 30

def command_thread():
    global threshold, scale
    while True:
        # Ждем ввода команды, например: t 2500 или s 10
        cmd = input("Command> ") 
        try:
            parts = cmd.split()
            if parts[0] == 't': # Порог
                val = int(parts[1])
                threshold = val
                sock.sendto(f"T{val}".encode(), (ESP32_IP, UDP_PORT))
            elif parts[0] == 's': # Скейл (время развертки)
                val = int(parts[1])
                scale = val
                sock.sendto(f"S{val}".encode(), (ESP32_IP, UDP_PORT))
            elif parts[0] == 'f': # Sampling frequency
                val = int(parts[1])
                sock.sendto(f"F{val}".encode(), (ESP32_IP, UDP_PORT))
            #elif parts[0] == 'q': # Скейл (время развертки)
            #    exit(0)
        except:
            print("Ошибка команды! Формат: 't 2000' или 's 2'")

threading.Thread(target=command_thread, daemon=True).start()


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

        print(f"Current Trigger Threshold: {threshold}")
    except socket.timeout:
        continue
