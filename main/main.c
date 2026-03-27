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

#define PORT 8080

static void tcp_server_task(void *pvParameters) {
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
        uint8_t buffer[256];
        uint32_t ret_num = 0;
        adc_continuous_handle_t adc_handle = (adc_continuous_handle_t)pvParameters;

        while (1) {
            esp_err_t ret = adc_continuous_read(adc_handle, buffer, 256, &ret_num, 0);
            if (ret == ESP_OK) {
                // Шлем сырые байты в сокет
                int err = send(sock, buffer, ret_num, 0);
                if (err < 0) {
                    ESP_LOGE("TCP", "Error occurred during sending: errno %d", errno);
                    break;
                }
            }
            vTaskDelay(pdMS_TO_TICKS(10)); 
        }

        shutdown(sock, 0);
        close(sock);
    }
}

static const char *TAG = "SCOPE";
#define READ_LEN 256

void app_main(void) {
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
        .max_store_buf_size = 1024,
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

	

	xTaskCreate(tcp_server_task, "tcp_server", 4096, (void*)handle, 5, NULL);
   // uint8_t result[READ_LEN];
   // uint32_t ret_num = 0;


   // while (1) {
   //     // Читаем данные из DMA
   //     esp_err_t ret = adc_continuous_read(handle, result, READ_LEN, &ret_num, 0);
   //     
   //     if (ret == ESP_OK) {
   //         for (int i = 0; i < ret_num; i += SOC_ADC_DIGI_RESULT_BYTES) {
   //             adc_digi_output_data_t *p = (adc_digi_output_data_t*)&result[i];
   //             // Просто выводим значение в консоль для теста
   //             printf("%lu\n", (uint32_t)p->type1.data);
   //         }
   //     }
   //     vTaskDelay(pdMS_TO_TICKS(100)); // Задержка, чтобы успеть рассмотреть цифры
   // }
}
