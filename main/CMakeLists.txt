idf_component_register(SRCS "main.c"
							"wifi.c"
							"pwm.c"
                    INCLUDE_DIRS "."
					PRIV_REQUIRES esp_wifi esp_event nvs_flash esp_adc esp_driver_dac esp_driver_ledc)

