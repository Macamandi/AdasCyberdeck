#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "driver/twai.h"

// Pinos
#define TX_PIN           GPIO_NUM_21
#define RX_PIN           GPIO_NUM_22

#define SW1_PIN          GPIO_NUM_13 // Bit 0
#define SW2_PIN          GPIO_NUM_14 // Bit 1
#define SW3_PIN          GPIO_NUM_27 // Bit 2

#define BTN_MAIS_PIN     GPIO_NUM_32
#define BTN_MENOS_PIN    GPIO_NUM_33

// IDs CAN
#define ID_DRIVE        0x50
#define ID_RE           0x60
#define ID_BCM          0x200
#define ID_VEL          0x100
#define ID_VOLANTE      0x101
#define ID_FRENTE       0x400
#define ID_TRAS         0x401

// Variáveis de Estado (Memória do Carro)
uint8_t vel = 0;
uint8_t volante = 90; // Centro (0 a 180 = -90 a 90 graus)
uint8_t dist_f = 200;
uint8_t dist_t = 200;
uint8_t portas = 0;
uint8_t seq_portas[] = {0x00, 0x01, 0x03, 0x0F, 0x3F};
int idx_portas = 0;

// Função mista: Manda pro TJA1050 (Físico) e pro Python (Serial)
void enviar_pacote(uint32_t id, uint8_t payload) {
    // 1. Envia para a Maletinha (Python)
    printf("0x20 0x07 0x%lx 0x%02x 0x00 0x00 0x1f\n", id, payload);

    // 2. Envia para a Rede Física (Sem esperar ACK)
    twai_message_t tx_msg = {.identifier = id, .extd = 0, .rtr = 0, .data_length_code = 1, .data = {payload}};
    twai_transmit(&tx_msg, pdMS_TO_TICKS(50));
}

// Lê as 3 chaves e retorna um número de 0 a 7
uint8_t ler_ferramenta_selecionada() {
    // A leitura  pull-up
    uint8_t bit0 = (gpio_get_level(SW1_PIN) == 0) ? 1 : 0;
    uint8_t bit1 = (gpio_get_level(SW2_PIN) == 0) ? 1 : 0;
    uint8_t bit2 = (gpio_get_level(SW3_PIN) == 0) ? 1 : 0;
    return (bit2 << 2) | (bit1 << 1) | bit0;
}

void painel_task(void *arg) {
    bool btn_mais_anterior = true;
    bool btn_menos_anterior = true;

    while (1) {
        bool btn_mais_atual = gpio_get_level(BTN_MAIS_PIN);
        bool btn_menos_atual = gpio_get_level(BTN_MENOS_PIN);
        uint8_t ferramenta = ler_ferramenta_selecionada();

        // Detecta o botão MAIS emorda de descida
        if (btn_mais_anterior == true && btn_mais_atual == false) {
            switch(ferramenta) {
                case 1: // Marcha D
                    enviar_pacote(ID_DRIVE, 0x00); break;
                case 2: // Portas
                    idx_portas = (idx_portas + 1) % 5;
                    enviar_pacote(ID_BCM, seq_portas[idx_portas]); break;
                case 3: // Volante
                    if (volante < 180) volante += 15;
                    enviar_pacote(ID_VOLANTE, volante); break;
                case 4: // Sensor Frente
                    if (dist_f < 200) dist_f += 10;
                    enviar_pacote(ID_FRENTE, dist_f); break;
                case 5: // Sensor Trás
                    if (dist_t < 200) dist_t += 10;
                    enviar_pacote(ID_TRAS, dist_t); break;
                case 6: // Velocidade (Bônus para os 8 estados)
                    if (vel < 120) vel += 5;
                    enviar_pacote(ID_VEL, vel); break;
            }
        }

        // Detecta o botão MENOS é apertado em Borda de descida)
        if (btn_menos_anterior == true && btn_menos_atual == false) {
            switch(ferramenta) {
                case 1: // Marcha R
                    enviar_pacote(ID_RE, 0x00); break;
                case 2: // Portas (Cicla pra trás)
                    idx_portas = (idx_portas == 0) ? 4 : idx_portas - 1;
                    enviar_pacote(ID_BCM, seq_portas[idx_portas]); break;
                case 3: // Volante
                    if (volante > 0) volante -= 15;
                    enviar_pacote(ID_VOLANTE, volante); break;
                case 4: // Sensor Frente
                    if (dist_f > 10) dist_f -= 10;
                    enviar_pacote(ID_FRENTE, dist_f); break;
                case 5: // Sensor Trás
                    if (dist_t > 10) dist_t -= 10;
                    enviar_pacote(ID_TRAS, dist_t); break;
                case 6: // Velocidade
                    if (vel > 0) vel -= 5;
                    enviar_pacote(ID_VEL, vel); break;
            }
        }

        btn_mais_anterior = btn_mais_atual;
        btn_menos_anterior = btn_menos_atual;
        vTaskDelay(pdMS_TO_TICKS(20)); // Debounce de 20ms
    }
}

void app_main(void) {
    // 1. Configura GPIOs (Inputs com Pull-Up)
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL<<SW1_PIN) | (1ULL<<SW2_PIN) | (1ULL<<SW3_PIN) | (1ULL<<BTN_MAIS_PIN) | (1ULL<<BTN_MENOS_PIN),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = 1,
        .pull_down_en = 0,
        .intr_type = GPIO_INTR_DISABLE
    };
    gpio_config(&io_conf);

    // 2. Configura CAN (TWAI) no modo NO_ACK
    twai_general_config_t g_config = TWAI_GENERAL_CONFIG_DEFAULT(TX_PIN, RX_PIN, TWAI_MODE_NO_ACK);
    twai_timing_config_t t_config = TWAI_TIMING_CONFIG_500KBITS();
    twai_filter_config_t f_config = TWAI_FILTER_CONFIG_ACCEPT_ALL();

    ESP_ERROR_CHECK(twai_driver_install(&g_config, &t_config, &f_config));
    ESP_ERROR_CHECK(twai_start());

    // 3. Inicia a Tarefa
    xTaskCreate(painel_task, "painel_task", 4096, NULL, 5, NULL);
}
