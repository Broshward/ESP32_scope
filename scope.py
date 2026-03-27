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

# Функция для чтения клавиши без Enter
def getch():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

def keyboard_listener():
    global threshold
    print("Управление: W - порог выше, S - порог ниже")
    while True:
        key = sys.stdin.read(1) # Нужно нажимать Enter или использовать библиотеку 'getch'
        if key == 'w':
            threshold = min(threshold + 100, 4000)
            sock.sendto(f"T{threshold}".encode(), (ESP32_IP, UDP_PORT))
        elif key == 's':
            threshold = max(threshold - 100, 100)
            sock.sendto(f"T{threshold}".encode(), (ESP32_IP, UDP_PORT))
        elif key == 'q':
            sys.exit(0)

# Запускаем поток команд
threading.Thread(target=keyboard_listener, daemon=True).start()


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
