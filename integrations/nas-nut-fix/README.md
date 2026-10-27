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
