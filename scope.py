#!/usr/bin/python

import socket
import numpy as np
import sys
import threading
import termios,tty

# Настройки
ESP32_IP = "192.168.1.51"
UDP_PORT = 8080
WIDTH = 120
HEIGHT = 30

v_threshold = 2000
sample_freq = 2000000
t_scale = 1

def command_thread():
    global v_threshold, sample_freq, t_scale
    # Печатаем приглашение один раз в самом низу
    sys.stdout.write("\033[%d;1H\033[KCommand> " %(HEIGHT+3))
    sys.stdout.flush()
    
    while True:
        # Пустой input не перебивает наши координаты курсора
        cmd = sys.stdin.readline().strip() 
        if not cmd:
            sys.stdout.write("\033[%d;1H\033[KCommand> " %(HEIGHT+3))
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
            #elif parts[0] == 'q': # Скейл (время развертки)
            #    exit(0)
        except Exception as e:
            # Выводим ошибку на 29-ю строку, чтобы не ломать график
            sys.stdout.write(f"\033[%d;1H\033[KError: {e}" %(HEIGHT+2))
            
        # Очищаем строку ввода для следующей команды
        sys.stdout.write("\033[%d;1H\033[KCommand> " %(HEIGHT+3))
        sys.stdout.flush()

threading.Thread(target=command_thread, daemon=True).start()


sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("", UDP_PORT)) # Слушаем всех на этом порту
sock.settimeout(0.5)
print("Осциллограф запущен. Жду UDP пакеты...")

while True:
    try:
        data_raw, addr = sock.recvfrom(2048)
        view = np.frombuffer(data_raw, dtype=np.uint16)[:WIDTH]
        
        # \033[s - СОХРАНИТЬ позицию курсора (где пользователь пишет команду)
        # \033[H - Прыгнуть в начало для графика
        sys.stdout.write("\033[s\033[H")
        
        frame = []
        # Рисуем график (HEIGHT строк)
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
            frame.append(line + "\033[K")
            
        # Выводим весь график разом
        sys.stdout.write("\n".join(frame) + "\n")
        sys.stdout.write(f"Trigger Threshold(t): {v_threshold} | Sampling freq(f): {sample_freq} | Time scale(s): {t_scale}")
        
        # \033[u - ВОССТАНОВИТЬ курсор обратно в Command>
        sys.stdout.write("\033[u")
        sys.stdout.flush()

    except socket.timeout:
        continue

