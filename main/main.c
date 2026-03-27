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

#include "wifi.h"

#define READ_LEN 1024
#define PORT 8080

static void tcp_server_task(void *pvParameters) 
{
    char addr_str[128];
    int addr_family = AF_INET;
    int ip_protocol = IPPROTO_IP;

    struct sockaddr_in dest_addr;
    dest_addr.sin_addr.s_addr = htonl(INADDR_ANY);
    dest_addr.sin_family = AF_INET;
    dest_addr.sin_port = htons(PORT);

    int listen_sock = socket(addr_family, SOCK_STREAM, ip_protocol);
    bind(listen_sock, (struct sockaddr *)&dest_addr, sizeof(dest_addr));
    listen(listen_sock, 1);

    ESP_LOGI("TCP", "Server listening on port %d", PORT);

    while (1) {

        struct sockaddr_storage source_addr;
        socklen_t addr_len = sizeof(source_addr);
        int sock = accept(listen_sock, (struct sockaddr *)&source_addr, &addr_len);
        
        if (sock < 0) {
            ESP_LOGE("TCP", "Unable to accept connection");
            break;
        }

        ESP_LOGI("TCP", "Client connected!");

        // Сюда мы передадим хендл АЦП и будем слать данные
        uint16_t buffer[READ_LEN];
        uint32_t ret_num = 0;
        adc_continuous_handle_t adc_handle = (adc_continuous_handle_t)pvParameters;


#define THRESH_LOW  1800
#define THRESH_HIGH 2200
#define FRAME_SIZE  512

		int opt = 1;
		setsockopt(sock, IPPROTO_TCP, TCP_NODELAY, &opt, sizeof(opt));
		int snd_size = FRAME_SIZE * 2; // Ровно один кадр
		setsockopt(sock, SOL_SOCKET, SO_SNDBUF, &snd_size, sizeof(snd_size));
		
		// Используем uint16_t, чтобы вместить значения до 4095
		uint16_t frame_to_send[FRAME_SIZE]; 
		uint8_t raw_dma_buffer[FRAME_SIZE * 4]; // Временный сырой буфер (с запасом)

		while (1) {
			uint32_t ret_num = 0;
			// Читаем данные из DMA (в байтах)
			esp_err_t ret = adc_continuous_read(adc_handle, raw_dma_buffer, sizeof(raw_dma_buffer), &ret_num, 0);

			if (ret == ESP_OK && ret_num > 0) {
				// Указатель на данные как на 16-битные числа
				adc_digi_output_data_t *p = (adc_digi_output_data_t *)raw_dma_buffer;
				int count = ret_num / SOC_ADC_DIGI_RESULT_BYTES;

				// Ищем триггер
				bool ready_to_trigger = false; // Состояние "сигнал внизу"
				int start_idx = -1;

				for (int i = 0; i < count - FRAME_SIZE; i++) {
					uint16_t val = p[i].type1.data & 0xFFF;

					if (!ready_to_trigger && val < THRESH_LOW) {
						ready_to_trigger = true; // Сигнал опустился достаточно низко
					}

					if (ready_to_trigger && val > THRESH_HIGH) {
						start_idx = i; // Сработал! Сигнал уверенно пошел вверх
						break;
					}
				}

				if (start_idx != -1) {
					// Копируем и отправляем кадр
					for (int j = 0; j < FRAME_SIZE; j++) {
						frame_to_send[j] = p[start_idx + j].type1.data & 0xFFF;
					}
					send(sock, frame_to_send, FRAME_SIZE * 2, 0);
					
				}
			}
			// Увеличим паузу до 50мс (20 кадров/сек), чтобы Wi-Fi "дышал" свободнее
			vTaskDelay(pdMS_TO_TICKS(50)); 
		}

        shutdown(sock, 0);
        close(sock);
    }
}

static const char *TAG = "SCOPE";

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
        .sample_freq_hz = 100 * 1000, // Для начала 100 кГц, чтобы не завалить лог
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
    ESP_ERROR_CHECK(adc_continuous_start(handle));

	

	xTaskCreate(tcp_server_task, "tcp_server", 10096, (void*)handle, 5, NULL);
}
