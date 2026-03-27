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
#include "conf.h"

#define PORT 8080
#define UDP_PORT       8080
#define FRAME_SIZE     512            // Количество точек в одном кадре
#define THRESH_LOW     1800           // Гистерезис: порог внизу
#define THRESH_HIGH    2200           // Гистерезис: порог вверху
#define READ_LEN       2048           // Размер сырого буфера для поиска триггера


static const char *TAG = "UDP_SCOPE";

void udp_scope_task(void *pvParameters) {
    adc_continuous_handle_t adc_handle = (adc_continuous_handle_t)pvParameters;
    
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
    
    ESP_LOGI(TAG, "UDP Scope started. Sending to %s:%d", PC_IP, UDP_PORT);

    while (1) {
        uint32_t ret_num = 0;
        // 2. Читаем данные из АЦП (DMA)
        esp_err_t ret = adc_continuous_read(adc_handle, raw_buf, READ_LEN, &ret_num, 0);

        if (ret == ESP_OK && ret_num > 0) {
            adc_digi_output_data_t *p = (adc_digi_output_data_t *)raw_buf;
            int count = ret_num / SOC_ADC_DIGI_RESULT_BYTES;

            bool ready_to_trigger = false;
            int start_idx = -1;

            // 3. Поиск триггера с гистерезисом
            for (int i = 0; i < count - FRAME_SIZE; i++) {
                uint16_t val = p[i].type1.data & 0xFFF;

                if (!ready_to_trigger && val < THRESH_LOW) {
                    ready_to_trigger = true;
                }

                if (ready_to_trigger && val > THRESH_HIGH) {
                    start_idx = i;
                    break;
                }
            }

            // 4. Отправка кадра, если триггер сработал
            if (start_idx != -1) {
                for (int j = 0; j < FRAME_SIZE; j++) {
                    frame_to_send[j] = p[start_idx + j].type1.data & 0xFFF;
                }

                sendto(sock, frame_to_send, FRAME_SIZE * sizeof(uint16_t), 0, 
                       (struct sockaddr *)&dest_addr, sizeof(dest_addr));

                // 5. Ограничение FPS (25-30 кадров в секунду)
                vTaskDelay(pdMS_TO_TICKS(40)); 
            }
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

	
	xTaskCreate(udp_scope_task, "udp_scope_task", 4096, (void*)handle, 5, NULL);

}
