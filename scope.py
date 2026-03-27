import socket
import os

# Настройки
ESP32_IP = '192.168.1.51' # Проверьте ваш IP из логов!
PORT = 8080
WIDTH = 120  # Ширина графика в символах
HEIGHT = 30 # Высота графика

def draw_plot(data):
    # Очистка экрана и возврат курсора (ANSI)
    print("\033[H\033[J", end="") 
    
    # Масштабируем данные АЦП (0-4095) в высоту терминала
    points = [int(val * (HEIGHT - 1) / 4095) for val in data[:WIDTH]]
    
    for row in range(HEIGHT - 1, -1, -1):
        line = ""
        for p in points:
            line += "█" if p == row else " "
        print(line)
    print("-" * WIDTH)

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((ESP32_IP, PORT))
    print("Connected to ESP32 Scope!")
    
    while True:
        # Читаем пачку данных (например, 256 байт)
        raw_data = s.recv(256) 
        if not raw_data: break
        
        # Преобразуем байты обратно в числа (учитывая структуру ADC_DIGI_OUTPUT_FORMAT_TYPE1)
        # Для ESP32 это обычно 2 байта на замер
        values = []
        for i in range(0, len(raw_data) - 1, 2):
            val = ((raw_data[i+1] << 8) | raw_data[i]) & 0xFFF
            values.append(val)
        
        if values:
            draw_plot(values)
