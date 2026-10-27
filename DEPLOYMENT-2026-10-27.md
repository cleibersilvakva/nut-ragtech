# Versão validada — proteção NAS, Mac mini e medições de internet

Inclui cliente NAS dedicado, recuperação segura no Pi, suspensão/WOL do Mac mini,
API Ookla pela Ethernet gigabit e relatório diário de recursos às 08h de Brasília.
Código e instaladores estão em integrations/. Não inclui chaves, tokens, bancos,
configurações privadas, binários de terceiros ou conteúdo do Brain.

29 testes de recuperação/patch/guard passaram, além dos testes dos demais módulos.
Cliente NUT real isolado validou OL, OB e estado crítico. Um evento crítico
simulado executou desligamento REAL; NAS retornou por WOL e cliente autenticou
após novo boot. Não houve novo corte físico da energia nessa validação.

## Configuração de produção

Raspberry: /opt/ragtech-monitor, NAS dedicado: nas-nut-client.service com perfil
/etc/nas-nut-client. O perfil padrão UGOS MODE=none é mantido intencionalmente.
Não ativar simultaneamente outro cliente. Recuperação exige NAS inacessível,
leituras recentes, gateway e OL/bateria >=80% por 180s. Não há WOL por timeout.

Mac mini: home-internet-monitor.service de usuário, Ethernet enp3s0f0 gigabit,
API autenticada na LAN. macmini-ups-power controla suspensão, nunca shutdown.
Limiares baseline versionados: NAS <=83%, Mac <=85%; teste temporário solicitado:
NAS <=88%, Mac <=86%, aplicado pelo script test-thresholds.py no Raspberry com
baseline persistente e ação restore. Não confundir baseline com override do teste.

## Credenciais

O daemon canônico usa /etc/ragtech-monitor/credentials.json ou RAGTECH_CREDENTIALS_FILE.
Modelo sem segredos em configs/credentials.example.json; instalar arquivo privado
root-only ANTES de substituir o daemon canônico numa implantação nova. Os patches
em produção preservam configuração local existente; esta publicação não troca a
forma de carregar credenciais da instalação que já está rodando.

Não executar deploy legado cegamente: seguir os instaladores por integração e
ler TEST-PLAN.md do NAS. Instalação inicial e correção de validação são comandos
diferentes. Validação real causa interrupção de dados/containers, usa autorização
de sudo de uso único e exige supervisor WOL prévio no Raspberry.

O teste isolado de validação para o cliente de produção temporariamente, pois o
upsmon privilegiado não admite concorrência. finally e ExecStopPost restauram
cliente em falha. A unidade não inicia no boot. Firmware UGOS não foi atualizado;
persistência foi provada no ciclo de desligamento/WOL, não em atualização de firmware.
