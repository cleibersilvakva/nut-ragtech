# Proteção NAS/NUT corrigida e validada

Documentação detalhada: TEST-PLAN.md. Configuração NAS em /etc/nas-nut-client;
serviço nas-nut-client.service chama binário real do UGOS, sem depender do wrapper
MODE=none em /etc/nut. Não sobrescrever o perfil privado com senhas em texto público.
Cliente e WOL ativos no novo boot; credencial só no staging privado NAS e perfil
root:nut0640. Nunca versionar credential.json.

Raspberry: nas_recovery.py no monitor, SHUTDOWNEXIT no e Restart=on-failure.
Recuperação exige ausência do NAS, gateway disponível, leituras recentes e OL>=80%
estável180s. Sem WOL em timeout, sem limpar FSD enquanto NAS online. Limiares do
último teste permanecem NAS<=83% e Mac<=85%; não foram revertidos automaticamente.

29 testes automatizados passaram e o evento crítico de NUT isolado executou
shutdown real. WOL, novo boot e reconexão autenticada de produção comprovados.
Não houve novo corte físico de energia. Arquivos de usuário não foram alterados.

A unidade de validação real exige root e não inicia no boot. Autorização de uso
único foi removida após teste. Não executar --real-poweroff como teste inofensivo.
Para novas instalações usar install-nas.sh somente sem cliente dedicado ativo;
para corrigir concorrência de validação, fix-validation.sh preserva produção.
Backup Pi: /var/backups/nut-safe-recovery-1793129604. Backup NAS:
/var/backups/nas-nut-client-1793129952. Falhas UGOS adicionais registradas no Brain.


## WOL pela Ethernet — versão validada

`wol_transport.py` vincula os três pacotes à eth0 e ao IPv4 da interface,
verifica link e calcula o broadcast. Erros chegam ao controlador, que persiste
falhas sem anunciar envio bem-sucedido e mantém no máximo três tentativas.
Atualização de instalação existente: `sudo sh install-wol-fix.sh`, somente
com UPS em OL, sem estado crítico; cria backup e reinicia ragtech-monitor.
Instalações novas com install-pi.sh também incluem essa correção.

Teste real de 27/10/2026 (horário de Brasília): desligamento normal manual,
WOL pelo Raspberry e retorno na primeira tentativa em cerca de 67 segundos.
Boot ID novo, cliente NUT, serviço WOL, SMB e /volume1 confirmados.
Esse teste não incluiu corte de energia elétrica.

`manual_wol_cycle.py` é um supervisor de teste explícito, não um serviço de boot:
aguarda desligamento manual por até 15 minutos, exige energia OL e bateria ≥80%,
aguarda pelo menos 180 segundos e tenta WOL até três vezes. As consultas de rede
podem prolongar os intervalos. Registra resultado no diretório do script.
Execute somente após preparar acesso de administração e acompanhar o teste.

Testes: `python3 -B -m unittest test_recovery test_wol_transport test_patch_pi test_validation_guard`.
