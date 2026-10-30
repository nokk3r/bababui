# Changelog

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
