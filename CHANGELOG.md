# Changelog

## Не выпущено

### RU

- Xray обновлён до 26.10.31: релиз 26.10.29 удалён из репозитория Xray-core, и образ перестал собираться. Сборка Docker теперь сверяет SHA-256 скачанных Xray, Hysteria и speedtest-go.
- Интерфейс переписан на Vue и собирается Vite. Исходники лежат в `frontend/`, образ Docker собирает их сам.
- Интерфейс опрашивает состояние раз в 2 секунды только во время проверки, в простое раз в 12 секунд, а на скрытой вкладке не опрашивает. Короткая проверка теперь сразу появляется в истории. Из `/api/state` убраны неиспользуемые `enabled_count` и `node_count`.
- Интерфейс теперь на английском по умолчанию, русский включается переключателем языка. Строки вынесены в `static/locales`, ошибки бэкенда переводятся в браузере. Столбец `error` в CSV теперь на английском.
- `docker-compose.prod.yml` публикует порт на `127.0.0.1` и не стартует без `WEB_PASSWORD`. Адрес и порт задаются через `BIND_HOST` и `PORT`.
- Несколько ссылок подписки в разных форматах загружаются полностью.
- Узлы с разным SNI, host, ключами REALITY или flow больше не склеиваются. История и галочка переносятся на новый id.
- Расписание считается только от проверок по расписанию. Ручная проверка и очистка истории его не сдвигают.
- Без ссылки подписки расписание не запускается.
- Остановленный замер не записывается в результаты узла.
- Пароль интерфейса может содержать не-ASCII символы.
- Сбой speedtest отделён от мёртвого узла: при неудачном замере трафик проверяется отдельным запросом, такой узел отмечается жёлтым. В результаты и CSV добавлено поле `alive`.
- Входящая и исходящая скорость меряются отдельными запусками на одном сервере, поэтому таймаут одного направления не стирает другое.
- Параллельные проверки не могут получить один локальный порт.
- Узлы с TLS поверх UDP (kcp, xhttp с h3) без снимка сертификата проверяются средствами Xray.
- Узлы с транспортами HTTP/2 и QUIC помечаются неподдерживаемыми: Xray их удалил.
- Образ теперь публикуется в `ghcr.io/nokk3r/bababui`. `docker-compose.prod.yml` смотрит туда же.

### EN

- Xray is updated to 26.10.31: the 26.10.29 release was removed from the Xray-core repository, which broke image builds. The Docker build now verifies the SHA-256 of the downloaded Xray, Hysteria, and speedtest-go.
- The interface is rewritten in Vue and built with Vite. Sources live in `frontend/`, and the Docker image builds them itself.
- The interface polls state every 2 seconds only during a check, every 12 seconds when idle, and not at all in a hidden tab. A short check now shows up in history right away. The unused `enabled_count` and `node_count` are gone from `/api/state`.
- The interface is now English by default, with Russian available from the language switcher. Strings live in `static/locales`, and backend errors are translated in the browser. The CSV `error` column is now in English.
- `docker-compose.prod.yml` publishes the port on `127.0.0.1` and refuses to start without `WEB_PASSWORD`. Set the address and port with `BIND_HOST` and `PORT`.
- Several subscription links in different formats now load in full.
- Nodes that differ by SNI, host, REALITY keys, or flow are no longer merged. History and the enabled flag move to the new id.
- The schedule counts only from scheduled runs. Manual checks and clearing history no longer shift it.
- The schedule does not run without a subscription link.
- A cancelled measurement is not recorded in the node's results.
- The interface password may contain non-ASCII characters.
- A speedtest failure is now separate from a dead node: after a failed measurement, traffic is checked with a separate request, and such a node is marked yellow. Results and CSV gain an `alive` field.
- Download and upload run separately on the same server, so a timeout in one direction no longer wipes the other.
- Parallel checks can no longer get the same local port.
- Nodes with TLS over UDP (kcp, xhttp with h3) that have no certificate snapshot are verified by Xray.
- Nodes using the HTTP/2 and QUIC transports are marked unsupported because Xray removed them.
- The image is now published to `ghcr.io/nokk3r/bababui`. `docker-compose.prod.yml` points there too.

## 0.2.0 — 2026-10-30

### RU

Скорость узла меряет speedtest-go 1.8.3 через SOCKS этого узла.

- HTTP-пинг, входящая и исходящая скорость идут на speedtest.net и пишутся в прежние поля результата.
- Сервер выбирается по адресу выхода узла. Объём зависит от скорости канала.
- Из настроек убраны лимиты секунд, мегабайты и адреса замера. Остались галочки входящей и исходящей скорости.
- Бинарник speedtest-go входит в образ.

### EN

Node speed is measured by speedtest-go 1.8.3 through that node's SOCKS proxy.

- HTTP ping, download, and upload go to speedtest.net and are stored in the same result fields.
- The server is chosen from the node's exit address. Transfer size follows the link speed.
- Second limits, megabyte caps, and probe URLs are gone from settings. Download and upload checkboxes remain.
- The speedtest-go binary is included in the image.

## 0.1.0

### RU

Первый выпуск: список узлов из подписки, проверка по расписанию, история в SQLite и веб-интерфейс.

### EN

First release: nodes from a subscription, scheduled checks, SQLite history, and a web interface.
