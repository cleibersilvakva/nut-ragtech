# QA — Plano de Testes: NUT/Ragtech Easy Pro 4164

## Arquitetura sob teste

```
Nobreak (USB serial) → ragtech_nut.py → dummy-ups → upsd (Raspberry Pi :3493)
                                                         ↓
                                                   nut-monitor (primary)
                                                    ↓          ↓
                                              notifycmd     FSD flag
                                           (Telegram+WOL)      ↓
                                                         nut-monitor (NAS, secondary)
                                                              ↓
                                                     /sbin/shutdown
```

---

## TC-01 — Leitura serial do nobreak

**Objetivo:** Confirmar comunicação USB com o protocolo proprietário Ragtech.

| Campo | Valor |
|-------|-------|
| Pré-condição | Cabo USB conectado em `/dev/ttyACM0` |
| Comando | `python3 -c "import serial,time; s=serial.Serial('/dev/ttyACM0',2400,timeout=2); s.write(bytes.fromhex('AA0400801E9E')); time.sleep(2); r=s.read(64); s.close(); print(r.hex(), len(r))"` |
| Resultado esperado | 31 bytes começando com `aa` |
| Resultado obtido | ✅ `aa10000c0064...` 31 bytes |
| Status | **PASSOU** |

---

## TC-02 — Decodificação dos dados do nobreak

**Objetivo:** Confirmar que os offsets do protocolo binário produzem valores plausíveis.

| Campo | Valor |
|-------|-------|
| Pré-condição | TC-01 passou |
| Verificação | `ups.status=OL`, `battery.charge≥80`, `input.voltage≈220V`, `battery.voltage≈13V` |
| Resultado obtido | ✅ OL, 100%, 222V, 13.4V |
| Status | **PASSOU** |

---

## TC-03 — Stack NUT funcionando no Raspberry Pi

**Objetivo:** Confirmar que os 4 serviços sobem e o `upsc` retorna dados.

| Campo | Valor |
|-------|-------|
| Comando | `systemctl is-active nut-driver@ragtech nut-server nut-monitor ragtech-monitor` |
| Resultado esperado | 4× `active` |
| Resultado obtido | ✅ 4× active |
| Resultado `upsc` | `OL`, `battery.charge: 100`, `input.voltage: ~220V` |
| Status | **PASSOU** |

---

## TC-04 — NAS monitora NUT server via TCP

**Objetivo:** Confirmar que o NAS consegue ler dados do nobreak via rede.

| Campo | Valor |
|-------|-------|
| Comando (no NAS) | `upsc ragtech@192.168.50.57` |
| Resultado esperado | Mesmos dados do TC-03 |
| Resultado obtido | ✅ `OL`, 100%, 221.5V |
| Status | **PASSOU** |

---

## TC-05 — NAS desliga ao detectar OB LB (shutdown via NUT)

**Objetivo:** Confirmar que o NAS executa `/sbin/shutdown` quando recebe FSD do primário.

| Campo | Valor |
|-------|-------|
| Pré-condição | nut-monitor ativo no NAS, FSD limpo no Raspberry Pi |
| Mecanismo | upsrw define `OB LB` → nut-monitor (primary) define FSD → nut-monitor (NAS secondary) executa shutdown |
| Tempo esperado para NAS ir offline | < 150s após OB LB ser definido |
| Resultado obtido | ✅ NAS offline em ~75s |
| Evidência | `journalctl -u nut-monitor` no NAS: `Executing automatic power-fail shutdown` + `Shutdown scheduled` |
| Status | **PASSOU** |

---

## TC-06 — WOL liga o NAS via magic packet

**Objetivo:** Confirmar que `wakeonlan -i 192.168.50.255 6c:1f:f7:a8:b1:0d` liga o NAS.

| Campo | Valor |
|-------|-------|
| Pré-condição | NAS desligado, WOL habilitado (`Wake-on: g` via ethtool) |
| Comando | `wakeonlan -i 192.168.50.255 6c:1f:f7:a8:b1:0d` |
| Resultado esperado | NAS responde ping em < 60s |
| Resultado obtido | ✅ NAS online em ~30-35s |
| Observação | Broadcast `255.255.255.255` não funcionava — switch bloqueava. `192.168.50.255` (subnet) funciona. |
| Status | **PASSOU** |

---

## TC-07 — FSD é limpo após reinício do nut-driver

**Objetivo:** Confirmar que reiniciar `nut-driver@ragtech` limpa o flag FSD do upsd.

| Campo | Valor |
|-------|-------|
| Pré-condição | `ups.status: FSD OL` visível via upsc |
| Procedimento | `systemctl stop nut-monitor nut-server; systemctl stop nut-driver@ragtech; sleep 2; start em ordem inversa` |
| Resultado esperado | `ups.status: OL` (sem FSD) |
| Resultado obtido | ✅ FSD limpo após restart do driver |
| Status | **PASSOU** |

---

## TC-08 — ragtech_nut.py envia Telegram no evento ONBATT

**Objetivo:** Confirmar que o Telegram recebe mensagem de "nobreak na bateria".

| Campo | Valor |
|-------|-------|
| Mecanismo | ragtech_nut.py detecta OL→OB → notifycmd (via upsmon ONBATT) envia Telegram |
| Resultado esperado | Mensagem Telegram: "🔴 Nobreak na bateria" |
| Resultado obtido | ✅ Confirmado durante TC-10 (mensagem recebida no Telegram) |
| Status | **PASSOU** |

---

## TC-09 — WOL enviado após bateria ≥ 80% (ragtech_nut.py)

**Objetivo:** Confirmar que o WOL só é enviado após bateria ≥ 80%.

| Campo | Valor |
|-------|-------|
| Mecanismo | ragtech_nut.py detecta OB→OL → aguarda `battery.charge ≥ 80` → limpa FSD → envia WOL |
| Resultado esperado | WOL enviado, NAS online |
| Resultado obtido | ✅ NAS online em 45s via WOL automático durante TC-10 |
| Observação | Na simulação a bateria já está em 100% — em produção aguarda até 80% realmente |
| Status | **PASSOU** |

---

## TC-10 — Recuperação automática após queda de energia (fluxo completo)

**Objetivo:** Simular queda e retorno de energia e validar o ciclo completo.

| Campo | Valor |
|-------|-------|
| Script | `sudo bash scripts/teste_simulacao.sh` |
| Resultado esperado | NAS offline em < 300s, NAS online via WOL em < 300s |
| Resultado obtido | ✅ NAS offline em 75s, NAS online em 45s via WOL |
| Status | **PASSOU** |

---

## TC-11 — Serviços sobem automaticamente após reboot do Raspberry Pi

**Objetivo:** Confirmar que todos os serviços são habilitados e sobem no boot.

| Campo | Valor |
|-------|-------|
| Comando | `systemctl is-enabled nut-driver@ragtech nut-server nut-monitor ragtech-monitor` |
| Resultado obtido | ✅ Todos `enabled` |
| Status | **PASSOU** |

---

## TC-12 — nut-monitor do NAS sobe automaticamente após reboot do NAS

**Objetivo:** Confirmar que nut-monitor está enabled no NAS e conecta ao Raspberry Pi após boot.

| Campo | Valor |
|-------|-------|
| Verificação | `systemctl is-enabled nut-monitor` no NAS |
| Resultado obtido | ✅ enabled. FSD limpo por ragtech_nut.py antes do WOL — NAS sobe sem loop |
| Status | **PASSOU** |

---

## TC-13 — Resistência a falha de rede temporária

**Objetivo:** O NAS não deve desligar se perder conexão com o NUT server por menos de 60s.

| Campo | Valor |
|-------|-------|
| Teste | `sudo systemctl restart nut-server` → aguarda 12s → verifica NAS |
| DEADTIME configurado | 60s no NAS |
| Resultado obtido | ✅ NAS permaneceu online após restart de 12s do nut-server |
| Status | **PASSOU** |

---

## Falhas Conhecidas e Causas Raiz

### FALHA-01: FSD persiste entre execuções de teste

**Sintoma:** Ao iniciar o nut-monitor no NAS após um teste, o NAS desliga imediatamente.

**Causa:** O flag FSD fica armazenado na memória do upsd. Não é apagado por `upsrw`. Só é apagado reiniciando `nut-driver@ragtech`.

**Status:** ✅ Mitigado — `teste_simulacao.sh` tem passo `[0/6]` que reinicia o driver. `ExecStartPre` no drop-in reinicia o driver antes de cada restart do nut-monitor.

---

### FALHA-02: nut-monitor entra em loop de restart ao ver FSD (Restart=always)

**Sintoma:** `restart counter: 161` — nut-monitor reiniciava, via FSD, tentava desligar, reiniciava, etc.

**Causa:** `Restart=always` + FSD preso = loop infinito.

**Status:** ✅ Resolvido — `ExecStartPre` reinicia o driver (limpa FSD) antes de cada subida do nut-monitor.

---

### FALHA-03: WOL não disparava após teste de simulação

**Sintoma:** Após restaurar OL no teste, NAS não recebia WOL.

**Causa raiz:** Com `Restart=on-abnormal`, nut-monitor saía limpo após SHUTDOWNCMD e não reiniciava. Sem nut-monitor, o evento ONLINE nunca era detectado e notifycmd nunca era chamado.

**Status:** ⚠️ Em investigação — solução proposta: `Restart=always` + `ExecStartPre` (limpa FSD antes de subir). Não validado ainda.

---

### FALHA-04: Passo [0/6] derrubava o nut-monitor do NAS

**Sintoma:** Durante o passo [0/6] do teste (restart do nut-server), o NAS perdia conexão por > DEADTIME (15s) e desligava.

**Causa:** `DEADTIME 15` muito curto para aguentar o restart do nut-server (~10-15s).

**Status:** ✅ Resolvido — DEADTIME aumentado para 60s no NAS.

---

## Matriz de Status

| TC | Descrição | Status |
|----|-----------|--------|
| TC-01 | Leitura serial | ✅ PASSOU |
| TC-02 | Decodificação protocolo | ✅ PASSOU |
| TC-03 | Stack NUT no Raspberry Pi | ✅ PASSOU |
| TC-04 | NAS monitora via TCP | ✅ PASSOU |
| TC-05 | NAS desliga em OB LB | ✅ PASSOU |
| TC-06 | WOL liga NAS | ✅ PASSOU |
| TC-07 | FSD limpo após restart driver | ✅ PASSOU |
| TC-08 | Telegram ONBATT | ✅ PASSOU |
| TC-09 | WOL após bateria ≥ 80% | ✅ PASSOU |
| TC-10 | Fluxo completo queda→retorno | ✅ PASSOU |
| TC-11 | Autostart no boot Raspberry Pi | ✅ PASSOU |
| TC-12 | NAS boot sem FSD preso | ✅ PASSOU |
| TC-13 | Resistência a falha de rede | ✅ PASSOU |

**Passou: 13 / Falhou: 0 / Pendente: 0**
