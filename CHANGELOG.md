# Changelog

## Не выпущено

### RU

- Ход проверки показывается в плавающей панели в углу экрана вместо полосы над таблицей: она не блокирует страницу, видна в любом разделе и сворачивается. В панели проверяемые узлы с этапом, готовые с итогом и скоростью и число узлов в очереди, а после конца — итог прогона. В строке проверяемого узла вместо времени виден этап. `current_ids` в прогрессе стоят в том же порядке, что имена и этапы.
- Колонка «Последние проверки» вместо «48 ч»: полоска, где столбик — проверка, цвет — её итог, высота — загрузка относительно лучшего замера. В таблице полоска фиксированной ширины на 24 последние проверки, на телефоне — сколько поместится, до 24. Новый `/api/recent` отдаёт последние проверки каждого узла, серия за 48 часов отдаёт `alive`.
- У графика узла своя легенда и подсказка у курсора в стиле интерфейса. Без наведения легенда показывает последний замер, а подсказка у сбоя показывает его причину. Сбои отмечены точкой у нижней оси.
- В окне узла причина сбоя идёт отдельной строкой под замером, без цветовых кодов терминала и меток времени, длинный текст сворачивается. Таблица помещается в телефон.
- Сортировка таблицы запоминается в браузере и не сбрасывается при перезагрузке.
- На телефоне в списке сортировки есть пункт «Без сортировки», и список больше не показывает ключ, по которому не сортирует.
- Кнопка «Назад» в браузере переключает разделы, а не уходит со страницы.
- Неподдерживаемый узел помечен «Протокол не поддерживается», а не «Трафик не идёт».
- Пока число узлов неизвестно, полоса прогресса бежит без процента. Несколько предупреждений в баннере идут отдельными строками.
- `/api/state` во время проверки отдаёт `current_ids`, а история узла содержит `alive`.
- Скорость можно показывать в Мбит/с или МБ/с: выбор в **Настройках → Общие** хранится в браузере. Время везде в 24-часовом формате.
- Интерфейс перенесён на shadcn-vue, Reka UI и Tailwind CSS. Появилась тёмная тема: системная, светлая или тёмная на выбор в **Настройках → Общие**. Шрифт Inter лежит в образе, внешних запросов нет.
- На обзоре первой идёт карточка «Работают» с числом рабочих узлов и разбивкой сбоев. Средние значения подписаны числом узлов, по которым они посчитаны.
- График узла переписан на uPlot: ось идёт по времени, неудачные проверки отмечены на графике, добавлены задержка и значения при наведении.
- Интерфейс работает на телефоне: узлы показаны карточками, навигация внизу экрана, страница больше не шире экрана.
- Сортировка и карточка узла доступны с клавиатуры, статус узла передаётся значком и подписью, контраст текста статусов повышен.
- В настройках одна кнопка сохранения и сброс изменений. Параллельность и срок хранения истории больше не блокируются при выключенном расписании: они действуют на любой запуск.
- Кнопка проверки узла отключена, пока идёт другая проверка. Очистка истории подтверждается в диалоге приложения. Без ссылки подписки обзор предлагает её добавить.
- Зависший узел больше не держит проверку по несколько минут. Перед замером узел проверяется на трафик не дольше 10 секунд, мёртвый сразу помечается сбоем. На одно направление speedtest даётся 25 секунд вместо 120, после таймаута загрузки отдача не запускается.
- В строке прогресса рядом с узлом показан этап: подключение, проверка трафика, загрузка или отдача.
- Полоса прогресса движется плавно, а не скачком после каждого узла. speedtest-go не сообщает ход замера, поэтому доля узла оценивается по времени его этапа. Назад полоса не откатывается.
- В карточке «Работают» нажатие на сегмент полосы или подпись под ней оставляет в списке только узлы с этим статусом. Фильтр статуса есть и рядом с фильтром протокола.
- Расписание можно задать выражением cron вместо интервала: режим выбирается в **Настройках → Расписание**. Время читается в часовом поясе браузера, пропущенные запуски не догоняются. Подсказка к параллельности переехала в тултип.
- Вкладка настроек «Проверка» переименована в «Замер», туда же переехала параллельность. Срок хранения истории теперь в **Настройках → Общие**.
- В истории можно удалить отдельный прогон: кнопка с корзиной в строке, удаление подтверждается. Результаты прогона пропадают из истории узлов и графиков. Идущий прогон удалить нельзя.
- Проверка начинается с узлов, которые давно не проверялись. Узел, упавший по таймауту, уходит в конец, и следующий запуск не начинается с него снова.

### EN

- Check progress lives in a floating panel in the corner instead of a bar above the table: it does not block the page, shows on every section, and collapses. It lists nodes being checked with their stage, finished nodes with their result and speed, and how many are queued, then a run summary at the end. The row of a node being checked shows its stage instead of the time. In progress, `current_ids` follow the same order as names and stages.
- The "Recent checks" column replaces "48 h": a strip with one bar per check, colored by result, with height showing download relative to the best check. In the table the strip has a fixed width for the last 24 checks; on phones it shows as many as fit, up to 24. The new `/api/recent` returns the latest checks of each node, and the 48-hour series returns `alive`.
- The node chart has its own legend and a tooltip at the cursor that match the interface. Without hovering, the legend shows the latest check, and a failed check shows its reason in the tooltip. Failures are marked with a dot on the bottom axis.
- In the node dialog, the failure reason sits on its own line under the check, without terminal color codes or log timestamps, and long text collapses. The table fits on a phone.
- Table sorting is remembered in the browser and survives a reload.
- On phones the sort list has a "No sorting" option, so it no longer shows a key the list is not sorted by.
- The browser Back button switches sections instead of leaving the page.
- An unsupported node is labeled "Protocol not supported" instead of "No traffic".
- While the node count is unknown, the progress bar runs without a percentage. Several banner warnings appear on separate lines.
- During a check, `/api/state` returns `current_ids`, and node history includes `alive`.
- Speed can be shown in Mbps or MB/s: the choice in **Settings → General** is stored in the browser. Times use the 24-hour clock everywhere.
- The interface moved to shadcn-vue, Reka UI, and Tailwind CSS. There is now a dark theme: pick system, light, or dark in **Settings → General**. The Inter font ships in the image, so nothing is loaded from outside.
- Overview now opens with a Working card showing the number of working nodes and a breakdown of failures. Averages state how many nodes they cover.
- The node chart is rewritten on uPlot: the axis follows time, failed checks are marked on the chart, and latency and hover values are added.
- The interface works on phones: nodes appear as cards, navigation sits at the bottom, and the page no longer overflows the screen.
- Sorting and node details work from the keyboard, node status has an icon and a label, and status text has higher contrast.
- Settings have one Save button and a way to discard changes. Concurrency and history retention are no longer locked when the schedule is off, because they apply to every run.
- A node's Check button is disabled while another check is running. Clearing history is confirmed in an app dialog. Without a subscription link, Overview offers to add one.
- A hanging node no longer holds a check for minutes. Before the speed test, the node gets at most 10 seconds to pass traffic, and a dead node fails right away. Each speedtest direction gets 25 seconds instead of 120, and upload is skipped after a download timeout.
- The progress line shows each node's stage next to its name: connecting, traffic check, download, or upload.
- The progress bar moves smoothly instead of jumping after each node. speedtest-go doesn't report progress mid-test, so each node's share is estimated from how long its current stage has run. The bar never moves backward.
- Clicking a segment of the Working bar or its label below filters the node list to that status. A status filter also sits next to the protocol filter.
- The schedule can use a cron expression instead of an interval: pick the mode in **Settings → Schedule**. Times use the browser's time zone, and missed runs are not caught up. The concurrency hint moved into a tooltip.
- The Check settings tab is renamed Measurement and now holds concurrency. History retention moved to **Settings → General**.
- A single run can be deleted from History with the trash button on its row, after a confirmation. Its results disappear from node history and charts. A run in progress can't be deleted.
- Checks start with the nodes tested longest ago. A node that timed out moves to the end, so the next run does not start with it again.

## 0.3.0 — 2026-11-02

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
