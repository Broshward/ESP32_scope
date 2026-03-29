#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_adc/adc_continuous.h"
#include "esp_log.h"

#include <string.h>
#include <sys/param.h>
#include "lwip/sockets.h"
#include "esp_wifi.h"
#include "nvs_flash.h"
#include "freertos/semphr.h"
#include "esp_task_wdt.h"

#include "wifi.h"
#include "conf.h"

#define PORT 8080
#define UDP_PORT       8080
#define FRAME_SIZE     128            // Количество точек в одном кадре
#define READ_LEN       8192           // Размер сырого буфера для поиска триггера

int g_threshold = 2000;
int g_thresh_low = 1800;
int g_thresh_high = 2200;
int g_scale = 1; // По умолчанию 1:1 (Масштаб времени)
bool g_trigger_enabled = false; // Trigger off
float g_gain = 1.0; // Коэффициент усиления (1.0 = без изменений)
int target_atten = ADC_ATTEN_DB_12; // Уровень аттенюации АЦП (hardware)
int32_t g_offset = 0; // Смещение в "попугаях" АЦП (от -2048 до 2048)
bool g_edge_rising = true; // true: Rising, false: Falling


// Семафор для защиты АЦП
volatile uint32_t target_freq = 100000;
volatile bool need_reconfig = false;


static const char *TAG = "UDP_SCOPE";

// Функция (пере)конфигурации
void configure_adc(adc_continuous_handle_t handle, uint32_t freq, adc_atten_t atten) 
{
    adc_continuous_config_t dig_cfg = {
        .sample_freq_hz = freq,
        .conv_mode = ADC_CONV_SINGLE_UNIT_1,
        .format = ADC_DIGI_OUTPUT_FORMAT_TYPE1,
    };
    adc_digi_pattern_config_t pattern = {
        .atten = atten, .channel = ADC_CHANNEL_6,
        .unit = ADC_UNIT_1, .bit_width = SOC_ADC_DIGI_MAX_BITWIDTH,
    };
    dig_cfg.pattern_num = 1;
    dig_cfg.adc_pattern = &pattern;
    
    ESP_ERROR_CHECK(adc_continuous_config(handle, &dig_cfg));
}

void feedback_command_task(void *pvParameters)
{
    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (sock < 0) {
        ESP_LOGE(TAG, "Unable to create socket: errno %d", errno);
        vTaskDelete(NULL);
        return;
    }
    // Добавляем bind, чтобы ESP32 слушала входящие пакеты на порту 8080
    struct sockaddr_in serv_addr;
    serv_addr.sin_addr.s_addr = htonl(INADDR_ANY);
    serv_addr.sin_family = AF_INET;
    serv_addr.sin_port = htons(UDP_PORT);
    bind(sock, (struct sockaddr *)&serv_addr, sizeof(serv_addr));

    char rx_buffer[16];
    struct sockaddr_in source_addr;
    socklen_t socklen = sizeof(source_addr);
 
	while(1){
        // ПРОВЕРКА КОМАНД (неблокирующая)
        int len = recvfrom(sock, rx_buffer, sizeof(rx_buffer) - 1, MSG_DONTWAIT, 
                           (struct sockaddr *)&source_addr, &socklen);
        if (len > 0) {
            rx_buffer[len] = 0;
            if (rx_buffer[0] == 'T') {
                g_threshold = atoi(&rx_buffer[1]);
                g_thresh_low = g_threshold - 150;
                g_thresh_high = g_threshold + 150;
                ESP_LOGI(TAG, "New Threshold set: %d", g_threshold);
            }
			if (rx_buffer[0] == 'S') {
				g_scale = atoi(&rx_buffer[1]);
				if (g_scale < 1) g_scale = 1;
				ESP_LOGI(TAG, "New Scale: %d", g_scale);
			}
			if (rx_buffer[0] == 'F') {
				uint32_t val = strtoul(&rx_buffer[1], NULL, 10);
				if (val >= 20000 && val <= 2000000) {
					target_freq = val;
					need_reconfig = true;
				}
			}
			if (rx_buffer[0] == 'M') { // Команда "m 0" или "m 1"
				g_trigger_enabled = atoi(&rx_buffer[1]);
				ESP_LOGI(TAG, "Trigger Mode: %s", g_trigger_enabled ? "ON" : "OFF");
			}
			if (rx_buffer[0] == 'G') {    // Команда "g 2.5"
				g_gain = atof(&rx_buffer[1]);
			}
			// В задаче управления ESP32:
			if (rx_buffer[0] == 'A') { // Команда "a 0", "a 1", "a 2", "a 3"
				int val = atoi(&rx_buffer[1]);
				adc_atten_t levels[] = {ADC_ATTEN_DB_0, ADC_ATTEN_DB_2_5, ADC_ATTEN_DB_6, ADC_ATTEN_DB_12};
				if (val >= 0 && val <= 3) {
					target_atten = levels[val];
					need_reconfig = true; // Сигнализируем основной задаче
				}
			}
			if (rx_buffer[0] == 'o') { // Команда "o -500"
				g_offset = atoi(&rx_buffer[1]);
			}			
			if (rx_buffer[0] == 'E') {
				g_edge_rising = atoi(&rx_buffer[1]);
			}			
        }
		vTaskDelay(pdMS_TO_TICKS(1000));
	}
}

void udp_scope_task(void *pvParameters) 
{
    adc_continuous_handle_t adc_handle = (adc_continuous_handle_t)pvParameters;
    adc_continuous_start(adc_handle);
	   
    // 1. Настройка UDP сокета
    struct sockaddr_in dest_addr;
    dest_addr.sin_addr.s_addr = inet_addr(PC_IP);
    dest_addr.sin_family = AF_INET;
    dest_addr.sin_port = htons(UDP_PORT);

    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (sock < 0) {
        ESP_LOGE(TAG, "Unable to create socket: errno %d", errno);
        vTaskDelete(NULL);
        return;
    }

    // Буферы
    uint8_t *raw_buf = malloc(READ_LEN);
    uint16_t *frame_to_send = malloc(FRAME_SIZE * sizeof(uint16_t));
#define DECIMATED_SIZE READ_LEN/2 // Буфер для поиска триггера
	uint16_t decimated_buf[DECIMATED_SIZE];
	uint16_t* send_ptr; // Указатель на то, что будем отправлять
    
    ESP_LOGI(TAG, "UDP Scope started. Sending to %s:%d", PC_IP, UDP_PORT);


    while (1) {
		// Это нужно для изменения параметров конфигурации АЦП
        if (need_reconfig) {
            adc_continuous_stop(adc_handle);
            configure_adc(adc_handle, target_freq, target_atten);
            adc_continuous_start(adc_handle);
            need_reconfig = false;
            ESP_LOGI("ADC", "Reconfigured to %lu Hz", target_freq);
			printf("%d\n",(int)target_freq);
        }
		

        // Читаем данные из АЦП (DMA)
		uint32_t ret_num = 0;
		esp_err_t ret = adc_continuous_read(adc_handle, raw_buf, READ_LEN, &ret_num, 0);

		if (ret == ESP_OK && ret_num > 0) {
			int count = ret_num / SOC_ADC_DIGI_RESULT_BYTES;
			adc_digi_output_data_t *p = (adc_digi_output_data_t *)raw_buf;

			// Программное усиление (масштабирование)
			for (int i = 0; i < count; i++) {
				uint16_t raw_val = p[i].type1.data & 0xFFF;
				int32_t centered = (int32_t)raw_val - g_threshold;	// - 2048;
				int32_t scaled = (int32_t)(centered * g_gain) + g_threshold + g_offset; // + 2048;
			
				// Ограничиваем (clipping), чтобы не вылезти за 0-4095
				if (scaled > 4095) scaled = 4095;
				if (scaled < 0) scaled = 0;
			
				p[i].type1.data = (uint16_t)scaled; // Записываем обратно
			}


			int start_idx = -1;
			bool ready = false;
			if (g_scale > 1) {
				// --- МЕДЛЕННЫЙ РЕЖИМ (Децимация) ---
				int d_count = 0;
				for (int i = 0; i < count && d_count < FRAME_SIZE * 2; i += g_scale) {
					decimated_buf[d_count++] = p[i].type1.data & 0xFFF;
				}
				
				// Поиск триггера по децимированным данным
				if (g_trigger_enabled)
					for (int i = 0; i < d_count - FRAME_SIZE; i++) {
						if (g_edge_rising) {
							if (!ready && decimated_buf[i] < g_thresh_low) ready = true;
							if (ready && decimated_buf[i] > g_thresh_high) { start_idx = i; break; }
						}
						else {
							if (!ready && decimated_buf[i] > g_thresh_high) ready = true;
							if (ready && decimated_buf[i] < g_thresh_low) { start_idx = i; break; }
						}
					}
				else
					start_idx = 0;
				send_ptr = &decimated_buf[start_idx];
			} 
			else {
				// --- БЫСТРЫЙ РЕЖИМ (Прямой поиск) ---
				if (g_trigger_enabled)
					for (int i = 0; i < count - FRAME_SIZE; i++) {
						uint16_t val = p[i].type1.data & 0xFFF;
						if (g_edge_rising) {
							if (!ready && val < g_thresh_low) ready = true;
							if (ready && val > g_thresh_high) { start_idx = i; break; }
						}
						else {
							if (!ready && val > g_thresh_high) ready = true;
							if (ready && val < g_thresh_low) { start_idx = i; break; }
						}
					}
				else
					start_idx = 0;

				// Формируем кадр напрямую из p (нужно скопировать в frame_to_send, т.к. p - структура)
				if (start_idx != -1) {
					for(int j=0; j<FRAME_SIZE; j++) frame_to_send[j] = p[start_idx+j].type1.data & 0xFFF;
					send_ptr = frame_to_send;
				}
			}

			if (start_idx != -1) {
				sendto(sock, send_ptr, FRAME_SIZE * 2, 0, (struct sockaddr *)&dest_addr, sizeof(dest_addr));
				vTaskDelay(pdMS_TO_TICKS(100)); 
			}
			else 
				vTaskDelay(pdMS_TO_TICKS(1));
		}
        // Небольшая пауза, чтобы не блокировать процессор полностью
		vTaskDelay(pdMS_TO_TICKS(1)); 
    }

    free(raw_buf);
    free(frame_to_send);
}

void app_main(void) 
{
    //Initialize NVS
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
      ESP_ERROR_CHECK(nvs_flash_erase());
      ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    if (CONFIG_LOG_MAXIMUM_LEVEL > CONFIG_LOG_DEFAULT_LEVEL) {
        /* If you only want to open more logs in the wifi module, you need to make the max level greater than the default level,
         * and call esp_log_level_set() before esp_wifi_init() to improve the log level of the wifi module. */
        esp_log_level_set("wifi", CONFIG_LOG_MAXIMUM_LEVEL);
    }

    ESP_LOGI(TAG, "ESP_WIFI_MODE_STA");
    wifi_init_sta();


    adc_continuous_handle_t handle = NULL;
    
    // 1. Конфигурация драйвера
    adc_continuous_handle_cfg_t adc_config = {
        .max_store_buf_size = READ_LEN*4,
        .conv_frame_size = READ_LEN,
    };
    ESP_ERROR_CHECK(adc_continuous_new_handle(&adc_config, &handle));

    // 2. Настройка параметров АЦП
    adc_continuous_config_t dig_cfg = {
        .sample_freq_hz = 2000 * 1000, // Для начала 100 кГц, чтобы не завалить лог
        .conv_mode = ADC_CONV_SINGLE_UNIT_1,
        .format = ADC_DIGI_OUTPUT_FORMAT_TYPE1,
    };

    adc_digi_pattern_config_t adc_pattern = {
        .atten = ADC_ATTEN_DB_12,
        .channel = ADC_CHANNEL_6, // GPIO 34
        .unit = ADC_UNIT_1,
        .bit_width = SOC_ADC_DIGI_MAX_BITWIDTH,
    };
    
    dig_cfg.pattern_num = 1;
    dig_cfg.adc_pattern = &adc_pattern;

    ESP_ERROR_CHECK(adc_continuous_config(handle, &dig_cfg));
    //ESP_ERROR_CHECK(adc_continuous_start(handle));

	
	//xTaskCreate(udp_scope_task, "udp_scope_task", 4096, (void*)handle, 5, NULL);
	xTaskCreatePinnedToCore(udp_scope_task, "udp_scope", 50000, (void*)handle, 
                        10,  // Высокий приоритет
                        NULL, 
                        1); // Ядро 1
	xTaskCreatePinnedToCore(feedback_command_task, "command_task", 4096, (void*)handle, 
                        1,  
                        NULL, 
                        0); // Ядро 

}
