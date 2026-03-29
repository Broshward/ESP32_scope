# ESP32_scope
Very simple console wifii oscilloscope for linux on ESP-WROOM-32 
Select your Wi-Fi network parameters in the "main/conf.h" and top of the "scope.py" files!


# 🚀 ESP32 CLI Network Oscilloscope

    A high-performance, "feng-shui" style oscilloscope in your terminal.
    Turn your ESP32 into a fast network-based measurement tool. 
    Minimalist, lag-free, and purely text-based (ANSI/VT100). 
    Perfect for debugging signals up to 3.3V, checking I2C/PWM, or just exploring the electromagnetic noise around you via a simple wire.


# 🔥 Key Features

    DMA-Powered Capture: Uses ESP32's ADC with DMA and Core 1 pinning for high-speed sampling (up to 2MHz).
    Advanced CLI Interface:
        Separate Command Zone: Type commands without flickering or overwriting the plot.
        Vector & Point Modes: Toggle between raw dots and connected lines (Bresenham-like).
        Smart Trigger: Hardware-based trigger with hysteresis and "Gain-aware" logic.
    On-the-fly Metrology: Real-time calculation of Vpp, RMS, Average Voltage, and Frequency.
    Visual Feng-Shui: Automatic grid calculation for Time/div and Volt/div.


# ⚡ Quick Start

1. Hardware Requirements

    ESP32 (WROOM/WROVER).
    Input Pin: GPIO 34 (ADC1_CH6).
    Signal Range: 0V to 3.3V ONLY.
    WARNING: ⚠️ Connecting higher voltages (like 220V or even 5V) will destroy your ESP32 instantly. Use a voltage divider for higher ranges!

2. Firmware (ESP-IDF)
   
    Install ESP-IDF SDK.
    Edit conf.h: set your Wi-Fi SSID/Password and your PC's IP address.
    Flash the chip:

    <code>
    idf.py build flash monitor
    </code>

3. Client (Python 3)
   Dependencies: numpy.
   <code>
   pip install numpy
   python3 scope.py
   </code>

   
### ⌨️ Command Console
Type commands at the `Command>` prompt and press **Enter**.


| Command | Parameter | Example | Description |
| :--- | :--- | :--- | :--- |
| **f** | `frequency` | `f 100000` | Set sampling rate (Hz) |
| **t** | `threshold` | `t 2500` | Set trigger level (0-4095) |
| **e** | `0 or 1` | `e 0` | Trigger edge (1: Rising, 0: Falling) |
| **s** | `value` | `s 10` | Time scale (decimation) |
| **a** | `0-3` | `a 3` | Hardware Attenuation (0:1.1V...3:3.3V) |
| **g** | `float` | `g 2.0` | Software Gain (Vertical zoom) |
| **o** | `int` | `o -500` | Vertical Offset (Shift trace) |
| **m** | `0 or 1` | `m 1` | Trigger Mode (1: Auto, 0: Roll) |
| **l** | `none` | `l` | Toggle Dots / Lines mode |
| **h** | `none` | `h` | Toggle Hold (Freeze frame) |


# 📡 Network Setup

Ensure your ESP32 and PC are on the same Wi-Fi network.

    Port: UDP 8080.
    Optimization: The script uses ANSI Save/Restore cursor codes (\033[s and \033[u). Best viewed in urxvt, xterm, or modern VS Code terminals.


# 📜 License
MIT. Feel free to fork, improve, and share!
