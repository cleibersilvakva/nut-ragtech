# Histórico de Instalação — 2026-04-22

## Topologia final

- **Raspberry Pi** (`raspberrypi`, 192.168.50.57) — NUT server, conectado ao nobreak via USB `/dev/ttyACM0`
- **NAS Ugreen DH4300 Plus** (192.168.50.110, MAC `6c:1f:f7:a8:b1:0d`) — NUT secondary, desliga em `OB LB`
- **Nobreak** Ragtech Easy Pro 4164 — protocolo binário proprietário, USB ID `04d8:000a`

---

## Passos realizados

### 1. Validação da comunicação serial com o nobreak

- Dispositivo reconhecido em `/dev/ttyACM0` (USB ID `04d8:000a`)
- Query `AA0400801E9E` retornou 31 bytes começando com `0xAA` (resposta válida)
- Dados decodificados: `OL`, bateria 100%, entrada 222V

**Observação:** timeout de 2s era insuficiente — necessário mínimo 2s de espera após write para resposta completa.

### 2. Deploy no Raspberry Pi

Credenciais configuradas:
- `upsmon_local`: `ragtech_local_2024`
- `upsmon_nas`: `ragtech_nas_2024`
- `admin`: `ragtech_admin_2024`
- Telegram BOT_TOKEN e CHAT_ID configurados em `notifycmd.py`

Arquivos deployados:
- `/etc/nut/` — `nut.conf`, `upsd.conf`, `ups.conf`, `upsd.users`, `upsmon.conf`, `ragtech.dev`
- `/etc/nut/notifycmd.py`
- `/opt/ragtech-monitor/ragtech_nut.py`
- `/etc/systemd/system/ragtech-monitor.service`
- Drop-ins: `nut-server.service.d/network-wait.conf`, `nut-monitor.service.d/restart.conf`

Serviços ativos: `nut-driver@ragtech`, `nut-server`, `nut-monitor`, `ragtech-monitor`

### 3. Deploy no NAS

- `nut-client` já estava instalado (2.8.0-7)
- `/etc/nut/nut.conf`: `MODE=netclient`
- `/etc/nut/upsmon.conf`: escrito via `sudo python3` (heredoc causava problemas no terminal)
- `nut-monitor` habilitado e ativo

### 4. Problemas encontrados e soluções

| Problema | Causa | Solução |
|----------|-------|---------|
| WOL não funcionava | `wakeonlan` enviava para `255.255.255.255` (bloqueado por switch/WiFi) | Alterado para `-i 192.168.50.255` (broadcast da subnet) |
| NAS não ligava com WOL | — | WOL respondeu em 5s após correção do endereço de broadcast |
| `FSD OL` preso após simulação | dummy-ups retém flag FSD | Reiniciar na ordem: stop nut-monitor → stop nut-server → stop nut-driver@ragtech → start na ordem inversa |
| Teste de simulação abortava em 120s | NAS demora ~115s para detectar OB LB e iniciar shutdown | Timeout aumentado para 300s |
| NAS ligava com bateria baixa | notifycmd enviava WOL imediatamente após ONLINE | Adicionado `wait_battery(80)` — aguarda bateria ≥ 80% antes de enviar WOL |
| Heredoc no NAS cortava conteúdo | Terminal adicionava indentação no delimitador | Usar `sudo python3 -c "open(...).write(...)"` para escrever arquivos |

### 5. Validação final

- **NAS desligou** via `OB LB` (confirmado pelo `journalctl` do NAS: `Executing automatic power-fail shutdown`)
- **WOL funcionou**: NAS online em 5s após `wakeonlan -i 192.168.50.255 6c:1f:f7:a8:b1:0d`
- Raspberry Pi tem duas interfaces: `eth0` (192.168.50.143) e `wlan0` (192.168.50.57) — NUT server usa wlan0

---

## Monitoramento do NAS (2026-04-22)

Adicionado monitoramento de disponibilidade do NAS em `ragtech_nut.py`:
- Ping a cada 30s para `192.168.50.110`
- Telegram `🔴 NAS offline` quando NAS para de responder
- Telegram `✅ NAS online` quando NAS volta

---

## Resultados de QA (2026-04-22)

| TC | Descrição | Status |
|----|-----------|--------|
| TC-01 | Leitura serial do nobreak | ✅ PASSOU |
| TC-02 | Decodificação protocolo binário | ✅ PASSOU |
| TC-03 | Stack NUT no Raspberry Pi | ✅ PASSOU |
| TC-04 | NAS monitora via TCP | ✅ PASSOU |
| TC-05 | NAS desliga em OB LB | ✅ PASSOU |
| TC-06 | WOL liga NAS | ✅ PASSOU |
| TC-07 | FSD limpo após restart driver | ✅ PASSOU |
| TC-08 | Telegram ONBATT | ✅ PASSOU |
| TC-09 | WOL após bateria ≥ 80% | ✅ PASSOU |
| TC-10 | Fluxo completo queda→retorno | ✅ PASSOU (NAS offline 75s, online 45s) |
| TC-11 | Autostart no boot Raspberry Pi | ✅ PASSOU |
| TC-12 | NAS boot sem FSD preso | ✅ PASSOU |
| TC-13 | Resistência a falha de rede | ✅ PASSOU |

Detalhes completos: `QA.md`

---

## Comandos úteis

```bash
# Status geral (no Raspberry Pi)
systemctl is-active nut-driver@ragtech nut-server nut-monitor ragtech-monitor
upsc ragtech@127.0.0.1 | grep -E "ups.status|battery|input.voltage"

# Limpar FSD preso
sudo systemctl stop nut-monitor nut-server ragtech-monitor
sudo systemctl stop nut-driver@ragtech
sleep 2
sudo systemctl start nut-driver@ragtech && sleep 2
sudo systemctl start nut-server && sleep 2
sudo systemctl start nut-monitor ragtech-monitor

# WOL manual para o NAS
wakeonlan -i 192.168.50.255 6c:1f:f7:a8:b1:0d

# Teste de simulação completo
sudo bash /home/cleibersilva/Dev/nut-ragtech/scripts/teste_simulacao.sh
```
