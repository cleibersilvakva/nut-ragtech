# Monitor de internet da casa

API local no Mac mini MiniCinnamon, Linux Mint, Ethernet enp3s0f0 negociada a
1000 Mbps full duplex, endereço observado 192.168.50.9 e gateway ASUS 192.168.50.1.
Mede velocidade disponível da conexão; não contabiliza tráfego por dispositivo.

## Fluxo

Raspberry → POST /v1/tests → medição Ookla no Mac mini → GET /v1/tests/<id> → histórico/Telegram.

API em http://192.168.50.9:8787, todas as rotas exigem Authorization: Bearer TOKEN.
POST sem corpo inicia medição assíncrona; chamadas concorrentes reutilizam o job.
Medição concluída há menos de 10 minutos pode ser reutilizada, com horário original
no resultado. Falhas têm espera de 60 segundos para nova tentativa.
GET /health indica processo ativo; GET /v1/tests/latest retorna a última tentativa.
SQLite local guarda até 90 dias (limpeza ao iniciar novos jobs). Jobs interrompidos
por restart são marcados como falha. Não há opção de comando/servidor arbitrário
fornecido pelo cliente. IPs permitidos em config.json; token privado em api.token.
Não publicar config.json, api.token, banco ou configuração /etc/macmini-speedtest.json.

## Medição

Cliente oficial Ookla 1.2.0.84 baixado por HTTPS de install.speedtest.net;
origem e hash do download em bin/OOKLA-SOURCE.txt. Não há hash publicado validado
independentemente para esse arquivo. Binário não versionado ou redistribuído.
Usa --interface=enp3s0f0; verifica carrier, velocidade do link, rota pelo ASUS e
IP interno no resultado, recusando VPN e origem diferente. Converte bandwidth
(bytes/s) para Mbps por multiplicação por 8/1e6. Sem resultado, não inventa zero
nem executa fallback no Raspberry. Perda não informada fica indisponível.
O servidor de teste e tráfego concorrente influenciam a velocidade medida.
LibreSpeed foi avaliado, mas a lista pública não apresentou servidores no Brasil.
Não é o backend em uso.

## Serviço Mac mini

systemctl --user status home-internet-monitor.service
systemctl --user restart home-internet-monitor.service
journalctl --user -u home-internet-monitor.service

Unidade habilitada em ~/.config/systemd/user; Linger=yes foi confirmado, permitindo
início sem login interativo. Mac mini deve estar ligado, acordado e com cabo ativo.
O IP atual usa DHCP: reservar 192.168.50.9 no ASUS evita mudanças na URL/configuração.
Não foi feita alteração no roteador nem aberta porta WAN. Token trafega em HTTP na
LAN; esta implantação pressupõe rede doméstica confiável.

## Instalação Raspberry

Staging: /home/cleibersilva/.local/share/macmini-speedtest

sudo sh /home/cleibersilva/.local/share/macmini-speedtest/install-raspberry.sh

Instalação concluída pelo usuário em 27/10/2026, com 4 testes OK e primeiro registro
Mac mini validado no histórico. Requer sudo para futuras instalações. Faz backup privado dos scripts e do SQLite;
instala cliente em /opt/ragtech-monitor e /opt/internet-monitor, token em /etc com
root:cleibersilva 0640; aplica alterações direcionadas e reinicia apenas os dois
monitores. Mede via API e envia primeiro relatório no Telegram. Não reinicia o Pi,
nem altera rotinas UPS/WOL. Em caso de falha, os arquivos anteriores e o banco estão
no diretório backup-macmini-api-<data> indicado pelo instalador; restauração manual.

Depois da ativação: #net no Telegram consulta o Mac mini; testes automáticos mantêm
intervalo de 1800 segundos. Ping de disponibilidade continua no Pi. Histórico antigo
fica marcado source=raspberry; novo source=macmini, incluindo jitter, interface,
servidor e horário original. O relatório diário de internet consolida apenas testes
Mac mini, sem misturar resultados limitados pela interface de 100 Mbps do Pi.
O relatório diário de recursos do Raspberry permanece independente.

## Testes

Mac mini: python3 -B -m unittest discover -s tests -v (9 testes).
Raspberry no staging: python3 -B -m unittest -v test_raspberry_integration (4 testes).
Testes simulados não enviam mensagens, não mexem no nobreak e não executam speedtest.
Primeiro teste real acionado pelo Pi: 792.7 Mbps download, 564.7 Mbps upload,
ping 3.004 ms, jitter 0.07 ms, servidor WIXX em Brasília, 27/10/2026 16:22:05 UTC.
Essa amostra não é garantia de desempenho sustentado da operadora.
