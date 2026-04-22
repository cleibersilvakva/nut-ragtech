# DDS — Sistema de Monitoramento de Nobreak com NUT
**Ragtech Easy Pro 4164 → NUT Server → Ugreen DH4300 Plus NAS**

Versão: 1.0 | Data: 2026-04-21 | Autor: Cleiber Silva

---

## 1. Objetivo

Monitorar o nobreak Ragtech Easy Pro 4164 (protocolo binário proprietário) e, em caso de queda de energia com bateria crítica, desligar de forma segura o NAS Ugreen DH4300 Plus. Quando a energia retorna, o NAS é religado automaticamente via Wake-on-LAN.

O MiniCinnamon (servidor NUT) **não desliga** — permanece de plantão na bateria.

---

## 2. Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                   Ragtech Easy Pro 4164                     │
│              Nobreak 1400VA / protocolo binário             │
└──────────────────────────┬──────────────────────────────────┘
                           │ USB /dev/ttyACM0
                           │ (CDC ACM, 2400 baud)
┌──────────────────────────▼──────────────────────────────────┐
│            MiniCinnamon — Ubuntu 24.04 — 192.168.50.20      │
│                                                             │
│  ┌─────────────────────┐    ┌──────────────────────────┐   │
│  │  ragtech-monitor    │    │  NUT Server (upsd)       │   │
│  │  (Python daemon)    │───▶│  dummy-ups driver        │   │
│  │  lê serial a cada 5s│    │  porta 0.0.0.0:3493      │   │
│  └─────────────────────┘    └──────────┬───────────────┘   │
│                                        │                    │
│  ┌─────────────────────┐               │                    │
│  │  upsmon (primary)   │◀──────────────┘                   │
│  │  SHUTDOWNCMD=/bin/true              │                    │
│  │  notifycmd → Telegram + WOL        │                    │
│  └─────────────────────┘               │                    │
└───────────────────────────────────────┼─────────────────────┘
                                        │ TCP :3493
┌───────────────────────────────────────▼─────────────────────┐
│              Ugreen DH4300 Plus — 192.168.50.110            │
│                                                             │
│  ┌─────────────────────┐                                    │
│  │  upsmon (secondary) │  OB LB → /sbin/shutdown -h +0     │
│  │  ragtech@192.168.50.20                                   │
│  └─────────────────────┘                                    │
└─────────────────────────────────────────────────────────────┘
```

### Fluxo de queda de energia

```
1. Energia cai
2. ragtech-monitor detecta input.voltage < 50V → seta OB no NUT
3. upsmon no MiniCinnamon dispara ONBATT → Telegram "🔴 nobreak na bateria"
4. NAS recebe OB via polling (5s)
5. Bateria cai abaixo de 25% → ragtech-monitor seta OB LB
6. upsmon no MiniCinnamon dispara LOWBATT → Telegram "⚠️ bateria crítica"
7. NAS recebe OB LB → upsmon executa /sbin/shutdown -h +0
8. NAS desliga com segurança
9. MiniCinnamon permanece ligado (SHUTDOWNCMD="/bin/true")

Quando a energia retorna:
10. ragtech-monitor detecta input.voltage > 50V → seta OL
11. upsmon no MiniCinnamon dispara ONLINE → Telegram "✅ energia voltou"
12. notifycmd.py aguarda 5s e envia WOL (3x) para 6c:1f:f7:a8:b1:0d
13. NAS recebe magic packet e liga
```

---

## 3. Por que não usa driver NUT padrão

O Ragtech Easy Pro 4164 usa protocolo binário proprietário — **não é compatível** com Megatec/Q1 (`blazer_ser`, `nutdrv_qx`).

- **USB ID:** `04d8:000a` (Microchip Technology)
- **Interface:** CDC ACM (serial emulada via USB)
- **Porta:** `/dev/ttyACM0`
- **Baud rate:** 2400
- Resposta a comandos Q1 padrão: sempre retorna `0xCA`

**Solução:** dummy-ups driver + daemon Python que lê o protocolo proprietário e publica os dados no NUT via `upsrw`.

---

## 4. Protocolo Proprietário Ragtech

> Fonte: engenharia reversa pela comunidade Home Assistant
> https://community.home-assistant.io/t/home-assistant-ragtech-nobreak-easy-pro-ups-monitoring/678828

### Comando de consulta

```
AA 04 00 80 1E 9E  (6 bytes)
```

### Resposta (31 bytes, inicia com AA)

| Offset | Campo             | Fórmula          | Unidade |
|--------|-------------------|------------------|---------|
| 0x08   | Carga da bateria  | valor × 0.392    | %       |
| 0x0B   | Tensão da bateria | valor × 0.0671   | V       |
| 0x0C   | Tensão de entrada | valor × 1.06     | V       |
| 0x0D   | Corrente de saída | valor × 0.1152   | A       |
| 0x0E   | Carga (load)      | direto           | %       |
| 0x0F   | Temperatura       | direto           | °C      |
| 0x1E   | Tensão de saída   | valor × 0.555    | V       |

### Lógica de status

```python
on_battery  = input_v < 50.0
low_battery = battery_pct < 25

status = "OB" if on_battery else "OL"
if on_battery and low_battery:
    status += " LB"
```

---

## 5. Inventário de Arquivos

### MiniCinnamon / Raspberry Pi (servidor NUT)

| Arquivo | Descrição |
|---------|-----------|
| `/opt/ragtech-monitor/ragtech_nut.py` | Daemon Python principal |
| `/etc/nut/nut.conf` | Modo do NUT (`netserver`) |
| `/etc/nut/ups.conf` | Definição do UPS dummy |
| `/etc/nut/ragtech.dev` | Estado inicial do dummy-ups |
| `/etc/nut/upsd.conf` | Endereço de escuta do upsd |
| `/etc/nut/upsd.users` | Usuários e senhas NUT |
| `/etc/nut/upsmon.conf` | Configuração do upsmon local |
| `/etc/nut/notifycmd.py` | Notificações Telegram + WOL |
| `/etc/systemd/system/ragtech-monitor.service` | Serviço systemd do daemon |
| `/etc/systemd/system/nut-server.service.d/network-wait.conf` | Aguarda rede antes de subir |

### Ugreen DH4300 Plus NAS (cliente NUT)

| Arquivo | Descrição |
|---------|-----------|
| `/etc/nut/nut.conf` | Modo `netclient` |
| `/etc/nut/upsmon.conf` | Monitor secundário |
| `/etc/systemd/system/nut-monitor.service.d/restart.conf` | Auto-restart em falha |

---

## 6. Conteúdo dos Arquivos de Configuração

### `/etc/nut/nut.conf`
```
MODE=netserver
```
> **Atenção:** `netserver` (não `standalone`). Com `standalone` o upsd rejeita conexões externas e o NAS não consegue conectar.

### `/etc/nut/ups.conf`
```ini
[ragtech]
    driver = dummy-ups
    port = /etc/nut/ragtech.dev
    desc = "Ragtech Easy Pro 4164"
```

### `/etc/nut/ragtech.dev`
```
battery.charge: 100
battery.voltage: 13.8
input.voltage: 220.0
output.voltage: 120.0
ups.load: 0
ups.temperature: 25
output.current: 0.0
ups.status: OL
```

### `/etc/nut/upsd.conf`
```
LISTEN 0.0.0.0 3493
MAXAGE 15
```
> **Atenção:** Use apenas `0.0.0.0`. Combinar `127.0.0.1` e `0.0.0.0` na mesma porta causa falha silenciosa onde o upsd não sobe na interface de rede — especialmente problemático com WiFi, onde o IP ainda não existe quando o serviço inicia.

### `/etc/nut/upsd.users`
```ini
[upsmon_local]
    password = CHANGE_ME_LOCAL
    upsmon primary

[upsmon_nas]
    password = CHANGE_ME_NAS
    upsmon secondary

[admin]
    password = CHANGE_ME_ADMIN
    actions = SET
    instcmds = ALL
```

### `/etc/nut/upsmon.conf` (servidor)
```
MONITOR ragtech@127.0.0.1 1 upsmon_local CHANGE_ME_LOCAL primary
MINSUPPLIES 1
SHUTDOWNCMD "/bin/true"
POLLFREQ 5
POLLFREQALERT 5
HOSTSYNC 15
DEADTIME 15
POWERDOWNFLAG /etc/killpower
NOTIFYCMD /etc/nut/notifycmd.py
RBWARNTIME 43200
NOCOMMWARNTIME 300
FINALDELAY 5

NOTIFYFLAG ONBATT  SYSLOG+EXEC
NOTIFYFLAG ONLINE  SYSLOG+EXEC
NOTIFYFLAG LOWBATT SYSLOG+EXEC
```
> **Atenção:** `SHUTDOWNCMD "/bin/true"` — o servidor NUT **não desliga**. Apenas o NAS desliga.

### `/etc/nut/upsmon.conf` (NAS — Ugreen UGOS Pro)
```
MONITOR ragtech@192.168.50.20 1 upsmon_nas CHANGE_ME_NAS secondary
MINSUPPLIES 1
SHUTDOWNCMD "/sbin/shutdown -h +0"
POLLFREQ 5
POLLFREQALERT 5
HOSTSYNC 15
DEADTIME 15
FINALDELAY 5
```
> No NAS, substituir `192.168.50.20` pelo IP do Raspberry Pi quando migrar.

---

## 7. Scripts

### `/opt/ragtech-monitor/ragtech_nut.py`
Ver arquivo: `scripts/ragtech_nut.py`

### `/etc/nut/notifycmd.py`
Ver arquivo: `scripts/notifycmd.py`

### `scripts/teste_simulacao.sh`
Script de teste completo sem desligar o nobreak fisicamente. Ver arquivo: `scripts/teste_simulacao.sh`

---

## 8. Serviços systemd

### `/etc/systemd/system/ragtech-monitor.service`
```ini
[Unit]
Description=Ragtech Easy Pro UPS Monitor (NUT bridge)
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/ragtech-monitor/ragtech_nut.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### `/etc/systemd/system/nut-server.service.d/network-wait.conf`
```ini
[Unit]
After=network-online.target
Wants=network-online.target
```
> Garante que o upsd só sobe após a interface de rede ter IP atribuído. Crítico para WiFi e para o Raspberry Pi.

### `/etc/systemd/system/nut-monitor.service.d/restart.conf` (NAS)
```ini
[Service]
Restart=always
RestartSec=30
```
> O upsmon do NAS para se perder conexão com o servidor. Com `Restart=always` e 30s de espera, ele reconecta automaticamente após o servidor voltar.

---

## 9. Procedimento de Instalação — Servidor NUT

### 9.1 Dependências

```bash
sudo apt update
sudo apt install -y nut-server nut-client python3-serial wakeonlan
```

### 9.2 Permissão USB

```bash
sudo usermod -aG dialout nut
```

### 9.3 Identificar porta do nobreak

```bash
ls /dev/ttyACM*
# Esperado: /dev/ttyACM0
# Se não aparecer, verifique: dmesg | grep tty
```

### 9.4 Testar comunicação com o nobreak

```bash
python3 -c "
import serial, time
s = serial.Serial('/dev/ttyACM0', 2400, timeout=2)
s.write(bytes.fromhex('AA0400801E9E'))
time.sleep(0.5)
r = s.read(64)
s.close()
print(r.hex())
# Esperado: aa21... (31+ bytes começando com AA)
"
```

### 9.5 Criar estrutura NUT

```bash
sudo mkdir -p /opt/ragtech-monitor
sudo cp ragtech_nut.py /opt/ragtech-monitor/
sudo chmod 755 /opt/ragtech-monitor/ragtech_nut.py
```

Criar `/etc/nut/ragtech.dev` com os valores iniciais (seção 6).

Criar todos os arquivos em `/etc/nut/` conforme seção 6.

Criar `/etc/nut/notifycmd.py` (seção 7), tornando-o executável:

```bash
sudo chmod 750 /etc/nut/notifycmd.py
sudo chown root:nut /etc/nut/notifycmd.py
```

### 9.6 Serviços systemd

```bash
# Copiar ragtech-monitor.service
sudo cp ragtech-monitor.service /etc/systemd/system/

# Drop-in network-wait para nut-server
sudo mkdir -p /etc/systemd/system/nut-server.service.d
sudo cp network-wait.conf /etc/systemd/system/nut-server.service.d/

sudo systemctl daemon-reload
sudo systemctl enable --now ragtech-monitor
sudo systemctl enable --now nut-server
sudo systemctl enable --now nut-monitor
```

### 9.7 Verificação

```bash
systemctl is-active ragtech-monitor nut-server nut-monitor
upsc ragtech@127.0.0.1 | grep -E "ups.status|battery|input.voltage"
# Esperado: ups.status: OL, battery.charge: 100, input.voltage: ~220
```

---

## 10. Procedimento de Instalação — NAS (Ugreen UGOS Pro)

```bash
ssh Cleibersilva@192.168.50.110

# Instalar NUT client se não presente
sudo apt install -y nut-client

# Configurar modo
echo "MODE=netclient" | sudo tee /etc/nut/nut.conf

# Adicionar monitor (substituir IP pelo do servidor NUT)
sudo nano /etc/nut/upsmon.conf
# Adicionar ao final:
# MONITOR ragtech@192.168.50.20 1 upsmon_nas CHANGE_ME_NAS secondary
# MINSUPPLIES 1
# SHUTDOWNCMD "/sbin/shutdown -h +0"
# POLLFREQ 5
# POLLFREQALERT 5
# HOSTSYNC 15
# DEADTIME 15
# FINALDELAY 5

# Drop-in restart automático
sudo mkdir -p /etc/systemd/system/nut-monitor.service.d
printf '[Service]\nRestart=always\nRestartSec=30\n' | sudo tee /etc/systemd/system/nut-monitor.service.d/restart.conf

sudo systemctl daemon-reload
sudo systemctl enable --now nut-monitor

# Verificar WOL habilitado
sudo ethtool eth0 | grep -i wake
# Esperado: Wake-on: g
```

---

## 11. Desktop Power Manager (se aplicável)

Se o servidor NUT roda com desktop (Cinnamon, GNOME), o gerenciador de energia pode desligar a máquina ao detectar bateria crítica via `upower`, **independentemente** do NUT.

**Desabilitar no Cinnamon:**
```bash
gsettings set org.cinnamon.settings-daemon.plugins.power critical-battery-action 'nothing'
```

**Desabilitar no GNOME:**
```bash
gsettings set org.gnome.settings-daemon.plugins.power critical-battery-action 'nothing'
```

No Raspberry Pi (sem desktop), este passo não é necessário.

---

## 12. Migração para Raspberry Pi

### Diferenças em relação ao MiniCinnamon

| Item | MiniCinnamon (Ubuntu x86_64) | Raspberry Pi (Raspberry Pi OS / Ubuntu arm64) |
|------|------------------------------|-----------------------------------------------|
| Arquitetura | x86_64 | arm64 |
| Porta USB serial | `/dev/ttyACM0` | `/dev/ttyACM0` (mesmo) |
| Desktop | Cinnamon — desabilitar power manager | Sem desktop — não é necessário |
| WiFi | Pode atrasar bind do upsd | Idem — network-wait.conf é crítico |
| Pacotes | `apt install` igual | `apt install` igual |
| Python serial | `python3-serial` | `python3-serial` |

### Passos adicionais no Raspberry Pi

```bash
# Se usar Raspberry Pi OS Lite (sem desktop), o processo é idêntico
# Não há gerenciador de energia para desabilitar

# Verificar que USB do nobreak aparece
lsusb | grep -i "04d8:000a"
ls /dev/ttyACM*

# Se precisar de permissão serial sem reiniciar:
sudo chmod 660 /dev/ttyACM0
sudo chown root:dialout /dev/ttyACM0
```

### Substituir IP no NAS após migração

No NAS, editar `/etc/nut/upsmon.conf` e trocar o IP:

```bash
ssh Cleibersilva@192.168.50.110
sudo sed -i 's/192.168.50.20/<IP_DO_RASPBERRY>/g' /etc/nut/upsmon.conf
sudo systemctl restart nut-monitor
```

### Checklist de migração

- [ ] Raspberry Pi com IP fixo configurado
- [ ] Nobreak USB conectado e reconhecido (`/dev/ttyACM0`)
- [ ] Comunicação serial testada (seção 9.4)
- [ ] Todos os arquivos NUT criados
- [ ] `network-wait.conf` instalado
- [ ] `ragtech-monitor` ativo e escrevendo no NUT
- [ ] `upsc ragtech@127.0.0.1` retorna `OL`
- [ ] NAS com IP do Raspberry Pi no `upsmon.conf`
- [ ] NAS `nut-monitor` ativo e conectado
- [ ] `journalctl -u nut-server | grep upsmon_nas` mostra login do NAS
- [ ] Teste de simulação executado com sucesso

---

## 13. Teste de Simulação

Executa sem desligar o nobreak fisicamente:

```bash
sudo bash scripts/teste_simulacao.sh
```

Sequência do teste:
1. Para `ragtech-monitor` (evita sobrescrever valores simulados)
2. Seta `OB` → Telegram "nobreak na bateria"
3. Seta `OB LB` + bateria 20% → NAS inicia shutdown
4. Aguarda NAS ficar offline (ping)
5. Seta `OL` → Telegram "energia voltou" + WOL enviado
6. Aguarda NAS responder ao ping
7. Reinicia `ragtech-monitor`

---

## 14. Troubleshooting

### NAS não desliga durante o teste

**Verificar:** `journalctl -u nut-server | grep upsmon_nas`
- Se não aparece login: NAS não está conectado ao upsd

**Causas comuns:**
1. `nut.conf` com `MODE=standalone` → mudar para `MODE=netserver`
2. `upsd.conf` com `LISTEN 127.0.0.1` → mudar para `LISTEN 0.0.0.0 3493`
3. `nut-monitor` inativo no NAS → `sudo systemctl restart nut-monitor`
4. upsd subiu antes da rede ter IP → reiniciar `nut-server` após rede estar up

### MiniCinnamon desligou junto com o NAS

**Causa:** Gerenciador de energia do desktop detectou bateria crítica via `upower`.

**Solução:** Ver seção 11 (Desktop Power Manager).

### Status `FSD OL` travado após simulação

O flag FSD fica no driver dummy-ups e faz o upsmon entrar em loop de restart.

```bash
sudo systemctl stop nut-monitor nut-server nut-driver@ragtech
sudo systemctl start nut-driver@ragtech
sleep 2
sudo systemctl start nut-server
sleep 2
upsc ragtech@127.0.0.1 ups.status   # deve mostrar OL sem FSD
sudo systemctl start nut-monitor
```

### upsd não aceita conexões externas

```bash
ss -tlnp | grep 3493
# Se mostrar só 127.0.0.1:3493:
# 1. Verificar /etc/nut/nut.conf → MODE=netserver
# 2. Verificar /etc/nut/upsd.conf → LISTEN 0.0.0.0 3493
# 3. sudo systemctl restart nut-server
```

### NAS não liga via WOL

```bash
# Verificar WOL habilitado no NAS
ssh Cleibersilva@192.168.50.110 "sudo ethtool eth0 | grep -i wake"
# Esperado: Wake-on: g

# Testar manualmente
wakeonlan 6c:1f:f7:a8:b1:0d
```

---

## 15. Referências

- NUT documentation: https://networkupstools.org/docs/
- Protocolo Ragtech (engenharia reversa): https://community.home-assistant.io/t/home-assistant-ragtech-nobreak-easy-pro-ups-monitoring/678828
- dummy-ups driver: https://networkupstools.org/docs/man/dummy-ups.html
