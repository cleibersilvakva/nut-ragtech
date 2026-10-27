# Avisos de boot do Raspberry e disponibilidade do NAS

Implantado no Raspberry em 27/10/2026 pelo usuário. Instalador e 12 testes
concluídos com sucesso; backup em `/opt/ragtech-monitor/backup-boot-notice-20261027-154518`.

O monitor avisa sobre o boot com início e horário do aviso em America/Sao_Paulo.
Reiniciar apenas o serviço não repete um envio confirmado. Falhas de envio são
repetidas a cada 30 segundos em thread separada. Estado em `/var/lib/ragtech-monitor/boot.json`.
A primeira ativação avisa sobre o boot já em andamento.

Sem motivo registrado, consulta evidências do boot anterior. Desligamento ordenado
não comprova causa; sem evidência, informa motivo não determinado. Não distingue
automaticamente queda de energia, travamento ou retirada da tomada.

NAS: aguarda 120 segundos após iniciar o monitor e estabelece linha de base
silenciosa com três pings iguais. Mudanças posteriores exigem três resultados
consecutivos. Os avisos descrevem acessibilidade, sem afirmar reboot do NAS.

## Testes isolados

```bash
cd scripts
python3 -B -m unittest -v test_lifecycle test_patch
sh -n install-boot-notice.sh
```

Nenhum teste acessa hardware, Telegram ou rede reais ou reinicia o sistema.

## Instalação

```bash
sudo sh scripts/install-boot-notice.sh
```

Preserva o daemon implantado, faz backup privado, aplica o patch e reinicia apenas
ragtech-monitor. Restaura o daemon anterior se o serviço não ficar ativo após 5s.
Não substitui outras configurações. Conferir serviço e confirmação real do Telegram.

## Reinícios planejados

Após o monitor registrar o boot atual:

```bash
sudo python3 /opt/ragtech-monitor/raspberry_lifecycle.py --reboot "Atualização do sistema operacional"
```

O comando registra o motivo e REINICIA o Raspberry. Reinícios fora dele podem ter
motivo não determinado. Marcadores de boots antigos não são utilizados.

## Limites

Falha entre Telegram aceitar e confirmação ser persistida pode duplicar o aviso;
estado removido/corrompido também pode gerar novo envio. Não há garantia de entrega
única. Avisos NAS mantêm envio simples; indisponibilidade inicial é baseline silenciosa.
