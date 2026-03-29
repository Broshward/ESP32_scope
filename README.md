# ESP32_scope
Very simple console wifii oscilloscope for linux on ESP-WROOM-32 

Select your Wi-Fi network parameters in the "conf.h" file!

🚀 ESP32 CLI Network Oscilloscope
A high-performance, "feng-shui" style oscilloscope in your terminal.
Turn your ESP32 into a fast network-based measurement tool. Minimalist, lag-free, and purely text-based (ANSI/VT100). Perfect for debugging signals up to 3.3V, checking I2C/PWM, or just exploring the electromagnetic noise around you via a simple wire.
🔥 Key Features

    DMA-Powered Capture: Uses ESP32's ADC with DMA and Core 1 pinning for high-speed sampling (up to 2MHz).
    Zero-Lag UDP Streaming: Unlike TCP, UDP packets fly instantly to your PC. No buffering, no 16-second delays.
    Advanced CLI Interface:
        Separate Command Zone: Type commands without flickering or overwriting the plot.
        Vector & Point Modes: Toggle between raw dots and connected lines (Bresenham-like).
        Smart Trigger: Hardware-based trigger with hysteresis and "Gain-aware" logic.
    On-the-fly Metrology: Real-time calculation of Vpp, RMS, Average Voltage, and Frequency.
    Visual Feng-Shui: Automatic grid calculation for Time/div and Volt/div.

⚡ Quick Start
1. Hardware Requirements

    ESP32 (WROOM/WROVER).
    Input Pin: GPIO 34 (ADC1_CH6).
    Signal Range: 0V to 3.3V ONLY.
    WARNING: ⚠️ Connecting higher voltages (like 220V or even 5V) will destroy your ESP32 instantly. Use a voltage divider for higher ranges!

2. Firmware (ESP-IDF)

    Install ESP-IDF SDK.
    Edit main.c: set your Wi-Fi SSID/Password and your PC's IP address.
    Flash the chip:
    bash

    idf.py build flash monitor

    Используйте код с осторожностью.

3. Client (Python 3)
Dependencies: numpy.
bash

pip install numpy
python3 scope.py

Используйте код с осторожностью.
⌨️ Command List & Examples
Type these commands in the Command> prompt at the bottom of your terminal:
Command	Action	Example	Description
f	Sampling Freq	f 200000	Set ADC frequency (20kHz - 2MHz).
t	Trigger Level	t 2500	Set trigger threshold (0-4095).
s	Time Scale	s 10	Software decimation (1 = 1:1, 10 = 10x compression).
a	HW Attenuation	a 0	Set HW range (0: 1.1V, 1: 1.5V, 2: 2.2V, 3: 3.3V).
g	Software Gain	g 2.5	Digital zoom for small signals.
o	Vertical Offset	o -500	Shift the trace up/down.
m	Trigger Mode	m 0	1: Triggered (Sync), 0: Roll (No-Sync).
l	Line Toggle	l	Toggle between dots and connected vectors.
k	Clipping	k	Hide noisy signals near 0V or 3.3V edges.
h	Hold	h	Freeze/Unfreeze the frame for analysis.
📡 Network Setup
Ensure your ESP32 and PC are on the same Wi-Fi network.

    Port: UDP 8080.
    Optimization: The script uses ANSI Save/Restore cursor codes (\033[s and \033[u). Best viewed in urxvt, xterm, or modern VS Code terminals.

📜 License
MIT. Feel free to fork, improve, and share!
