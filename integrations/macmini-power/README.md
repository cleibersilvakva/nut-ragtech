# Mac mini: suspensão e WOL pelo Raspberry/NUT

Política: 3 amostras distintas e recentes em OB com bateria <=85% solicitam suspensão.
Retorno exige OL, bateria >=80% e 180s de leituras contínuas; qualquer falha, lacuna
ou nova queda reinicia a contagem. Não acorda máquinas que o controlador não tenha
solicitado suspender. Estado persiste em /var/lib/macmini-ups-power/state.json.
Três tentativas máximas por ação. Falta de confirmação é relatada explicitamente.
WOL exige rede e alimentação de standby; enviar pacote não comprova despertar.

O Ragtech publica amostra após cada leitura válida do dispositivo. O novo serviço
recusa amostras com mais de 20s ou boot ID diferente, evitando decisões com o estado
antigo mantido pelo driver dummy. Não altera comandos/limiares do NAS nesta entrega.

## Instalação (concluída e validada em 27/10/2026)

No Mac mini:

sudo sh /home/cleiber/Dev/macmini-ups-power/install-macmini.sh

No Raspberry:

sudo sh /home/cleibersilva/.local/share/macmini-ups-power/install-raspberry.sh

A instalação Mac configura WOL e autoriza chave exclusiva com comando forçado,
origem .143 e sem encaminhamento/PTY. Sudoers só permite status e suspend no helper
root-owned. Não permite shell, reboot ou shutdown por essa chave. Suspensão é
agendada 8s depois da solicitação para permitir o retorno da chamada SSH.

Instalação Pi valida SSH antes de ativar, instala serviço separado e integra apenas
heartbeat ao Ragtech, preservando funções NAS/UPS. Sem amostra recente não habilita.
Backup do Ragtech: /opt/ragtech-monitor/ragtech_nut.py.before-macmini-power-<timestamp>.
Configuração não contém senha; chave privada dedicada fica apenas no Raspberry.
Host key Mac é fixada a partir da chave pública local, sem aceitar identidade cega.
O IP usa DHCP: alteração exige atualizar URL/SSH e autorização por IP.

## Validação

python3 -B -m unittest discover -s tests -v

22 testes simulados não suspenderam hardware, não cortaram energia e não enviaram
Telegram. Testes físicos de falta de energia não são executados por estes scripts.

Após instalar ambos, teste REAL no Raspberry (interrompe o Mac mini):

python3 /home/cleibersilva/.local/share/macmini-ups-power/validate_cycle.py

O teste agenda WOL independente no Raspberry antes de solicitar suspensão. Procura
um período inacessível seguido de retorno no mesmo boot. Confirmar também registros
de systemd-suspend e retorno do serviço home-internet-monitor no Mac após retomar.
Ciclo executado em 27/10/2026: offline observado, retorno em 59s no mesmo boot;
journal confirmou 38s de suspensão. Ethernet gigabit e API recuperadas. Se WOL falhar, ligar manualmente; software não garante
capacidade de wake do hardware. O controlador real não simula OB/LB no NUT.

## Inspeção e desativação

No Pi: systemctl status macmini-ups-power; journalctl -u macmini-ups-power
Desativar: sudo systemctl disable --now macmini-ups-power
Depois de desativar, o helper e a chave continuam instalados; não há novas ações
automáticas. Restaurar backup do Ragtech remove heartbeat se necessário, seguido
de reinício do monitor. Não apagar configurações NUT ou scripts de desligamento NAS.

## Limites

Uma confirmação SSH aceita comprova a solicitação, não a suspensão efetiva.
Inacessibilidade pode ser falha de rede. Confirmação física depende do teste real.
Se o processo morrer após a aceitação SSH e antes de salvar ownership, o despertar
pode exigir intervenção manual. Pacotes WOL não garantem chegada/despertar. Bloqueios
de suspensão do sistema não são ignorados. Telegram não é usado como controle.

Validação pós-implantação: SSH status permitido, comando fora da lista rejeitado
com código 126; amostra OL 100% recente; serviço enabled/active com NRestarts=0.
Mensagem de conclusão aceita pela API Telegram. Não foi cortada energia real.

Durante teste real, usuário alterou limiares: Mac mini <=85% e NAS <=83%.
Patch NAS aplicado diretamente ao read_ups em produção, com backup e testes de
fronteira 83/84% em bateria e 83% na rede. Recuperação mantém >=80%/180s para Mac.
