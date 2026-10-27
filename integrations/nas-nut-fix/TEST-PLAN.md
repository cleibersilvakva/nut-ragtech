# Plano e resultados: correção da proteção NAS

1. Baseline: confirmar OL sem FSD; preservar configuração existente e serviços UGOS.
2. Cliente real isolado no NAS, com credenciais fictícias e ação touch privada:
   OL sem ação; OB sem ação; OB LB/FSD executa ação configurada. PASSOU no NAS.
3. Recuperação: 21 testes unitários/de fluxo PASSARAM localmente: persistência,
   arquivo inválido, dados antigos/outro boot/lacunas, energia oscilando, bateria
   abaixo de 80%, NAS ainda ligado, gateway sem resposta, timeout sem WOL,
   confirmação de ausência/retorno, falha no clear-FSD, limite de tentativas e
   mudança de energia imediatamente antes do WOL.
4. Patch em código real Pi: idempotência e preservação AST de todas as funções fora
   main/clear_fsd/power_restored_sequence, incluindo protocolo, limiar NAS <=83%,
   integração Mac e API. PASSOU no Pi. Recuperação e primary com SHUTDOWNEXIT no /
   Restart=on-failure implantados com backup, serviços ativos e estado OL.
5. Ativação NAS: precisa sudo do usuário. Configuração própria em /etc/nas-nut-client;
   teste autenticado NAS→Pi antes de ativar, diretórios root:nut, cliente dedicado
   com binário real /usr/lib/nut/upsmon (2.8.0), sem wrapper UGOS que ignora MODE=none.
   Validar serviço active e conexão NAS .110 persistente no servidor, sem erros.
6. Teste real: após supervisor WOL no Pi estar pronto, iniciar unidade isolada de
   validação no NAS. O NUT real de teste recebe estado crítico sintético em loopback
   e usa a MESMA ação de desligamento normal da produção. Não altera status do
   nobreak real e não suspende Mac. NAS desliga; o supervisor usa leituras reais
   e só envia WOL após OL >=80% estável por 180s e três consultas offline, até 3
   tentativas. Validar retorno SSH/painel, novo boot, marcador origin=validation,
   serviço NUT automaticamente ativo e login no Pi. PENDENTE até instalação NAS.
7. Teste de persistência: o ciclo poweroff/WOL acima confirma auto-start do cliente
   e WOL no novo boot. Não afirma persistência após atualização de firmware UGOS.
8. Nenhuma nova retirada de energia física prevista nesta etapa. A regra de NUT e
   as ações reais serão cobertas separadamente; repetir outage físico só depois.

# Operação

No NAS:
sudo sh /home/cleibersilva/.local/share/nas-nut-fix/install-nas.sh

O instalador NÃO desliga o NAS. Instala serviço e perfil independentes, testa login,
configura WOL e deixa autorização sudo de USO ÚNICO para iniciar a unidade de teste
real. Ao executar o shutdown de validação, o helper remove essa autorização.
Só o comando fixo systemctl start --no-block nas-nut-validation.service é permitido;
não autoriza shell/comandos arbitrários. A unidade não é habilitada no boot.

O ciclo real interrompe o acesso aos dados/containers enquanto o NAS desliga e
reinicia. Normal poweroff passa pelo systemd, sem force ou corte de energia.
Se WOL não funcionar, ligar manualmente. Não declarar validação sem evidências.

# Rollback

Backups NAS em /var/backups/nas-nut-client-<timestamp>; arquivos padrão UGOS não são
reescritos. Desativar somente nas-nut-client.service e nas-nut-wol.service restaura
estado sem cliente dedicado (e sem proteção; informar usuário). Remover autorização
de validação se não for usada. Recuperação Pi: backup em
/var/backups/nut-safe-recovery-1793129604 (ragtech_nut.py, upsmon.conf, restart.conf).
Restaurar os três e reiniciar serviços somente com UPS normal e cliente coordenado.
A versão antiga tem recuperação insegura, por isso rollback não é solução permanente.

# Segredos

Credencial existe apenas no Pi e no arquivo privado credential.json no staging NAS,
depois perfil root:nut 0640. Nunca imprimir, copiar para README/vault ou versionar.
Cliente padrão UGOS permanece sem alteração; somente um daemon de proteção ativo.
Não foi feito push Git desta entrega.


# Correção da validação concorrente

A primeira unidade real falhou porque o upsmon root detecta a instância de
produção apesar dos diretórios distintos. A configuração isolada, por si só, não
permitiu duas instâncias privilegiadas. Cliente de produção permaneceu ativo.
Agora validation_guard verifica OL sem FSD antes de parar produção, verifica a
parada, executa teste único e restaura cliente em finally. ExecStopPost fornece
segunda restauração se o processo do teste for interrompido. Durante poweroff
(systemd stopping), não tenta reativar o cliente. 7 testes do guard passaram em
ambos os computadores; prova root completa será executada por fix-validation.sh,
que faz backup e NÃO desliga. Atualização em /opt e unidade exige sudo usuário.


# Resultado final

Fix-validation aplicado pelo usuário: 7 guard tests + parar/testar/restaurar root
passaram. Ciclo real repetido com supervisor PID17981 no Pi: NAS offline, estabilidade
180s, WOL e returned=true. Novo boot <boot-id>, marcador
origin=validation com boot anterior, cliente/WOL enabled/active e login NAS no Pi.
SMB, Docker, painel e volumes retornaram. Autorização temporária removida.
29 testes automatizados + provas isoladas e ação real concluídos. Não houve novo
corte de energia físico nem alteração de status do UPS de produção. Persistência
validada no novo boot, não em atualização UGOS. Três unidades UGOS apareceram
failed (domain_tool, rockchip, smbftpd), sem causa estabelecida; smbd/Docker ativos.
