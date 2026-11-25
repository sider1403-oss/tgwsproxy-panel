# tgwsproxy-panel

[![CI](https://github.com/sider1403-oss/tgwsproxy-panel/actions/workflows/ci.yml/badge.svg)](https://github.com/sider1403-oss/tgwsproxy-panel/actions/workflows/ci.yml)

Веб-панель администрирования для уже работающего
[Telegram WebSocket Proxy](https://github.com/valnesfjord/tg-ws-proxy-rs)
(`tg-ws-proxy-rs`, контейнер `tgwsproxy`) на базе Docker Compose.

Панель не устанавливает второй прокси и не меняет его архитектуру: она управляет существующим
контейнером через привилегированный helper (фиксированный allowlist), читает его журнал и конфигурацию, показывает сетевые сокеты
и пассивно определяет семейство устройства клиента.

> Проверено с `tg-ws-proxy 2.7.2` (образ `valnesfjord/tg-ws-proxy-rs`).
> Панель рассчитана на доверенную локальную сеть и требует входа администратора.

## Возможности

- **Дашборд** — статус и health, uptime, версия, активные сессии, клиенты, трафик в обе стороны,
  скорость, ошибки/предупреждения, CPU/RAM LXC и контейнера, графики трафика и подключений,
  распределение по DC. Карточки кликабельны и ведут в детализацию (`/clients`, `/metrics/*`,
  `/traffic`, `/dc`, `/connections`, `/logs`, `/service`).
- **Подключения** — активные TCP-сессии (IP, устройство, порт, длительность, TCP-счётчики,
  принудительный разрыв) и история из журнала с поиском, фильтрами, сортировкой и пагинацией.
- **Устройства** — приблизительное определение по TCP SYN (Windows, Apple/iOS/macOS, Android,
  Linux) с иконками и возможностью указать точный тип вручную для IP.
- **Ключи** — реальные ключи из `TG_SECRET`: показ, копирование `tg://`, создание,
  отключение/включение, удаление, комментарии. Для каждого ключа — отдельная LAN-ссылка
  и ссылка для внешних клиентов (см. ниже).
- **Логи** — уровни INFO/WARN/ERROR/DEBUG, категории, поиск, период, live-поток (SSE),
  детали, экспорт TXT/CSV, маскирование секретов.
- **Сервис** — запуск/остановка/перезапуск контейнера через helper, проверка порта,
  `docker logs`, действующая конфигурация, журнал действий администратора.
- **Диагностика** — быстрые проверки канала; сквозная MTProto-проба отключена
  (временные контейнеры запрещены), история старых проверок сохранена.
- **Уведомления** — Telegram-бот и/или webhook, правила, антидребезг, тест, история доставки.
- **Конфигурация** — просмотр и редактирование известных `TG_*` и `--dc-ip`, валидация,
  автоматический бэкап, применение с откатом, восстановление копий.
- **Тема** — тёмная по умолчанию, светлая по кнопке; выбор сохраняется в браузере.
- **Безопасность** — вход по логину и паролю (Argon2id), серверные сессии в SQLite,
  CSRF-защита, ограничение попыток входа, журнал безопасности, управление активными
  сессиями и принудительная смена пароля.
- **Лимиты** — ограничены `panel.log`, journald, Docker-лог, БД (retention + мягкий лимит),
  резервные копии; в UI есть карточка «Хранилище и лимиты логов».

## Архитектура

```
Браузер ──HTTP/SSE──> tgws-panel (FastAPI/uvicorn :8090, User=tgws-panel)
                          │
                          ├── SQLite (data/panel.db)
                          ├── /run/tgws-panel/helper.sock
                          │      └── tgws-panel-helper (root, allowlist):
                          │            docker status/logs/start/stop/restart/version
                          │            nsenter + ss (только tgwsproxy)
                          │            config apply/restore, backups, logs, proc
                          └── /run/tgws-panel-netmon/netmon.sock
                                 └── tgws-panel-netmon (CAP_NET_RAW):
                                       AF_PACKET TCP SYN fingerprint

React SPA (Vite) ── статика из frontend/
```

Основной процесс **не имеет** root, Docker Socket, `sudo` и группы `docker`.
Вспомогательный helper — единственный root-компонент; он принимает только
заранее определённые операции, проверяет `SO_PEERCRED` и параметры.
`tgws-panel-netmon` работает от отдельного пользователя с `CAP_NET_RAW` и не имеет
доступа к Docker, `.env` или базе панели.

## Требования

- Linux (проверено на Debian 12 / LXC), root — только для установки.
- Python 3.11+.
- Node.js 18+ и npm — только для сборки фронтенда.
- Уже установленный `tg-ws-proxy-rs` в Docker Compose (по умолчанию `/opt/tg-ws-proxy`,
  контейнер `tgwsproxy`, порт `1443`).
- Docker с логами `json-file` и лимитами (рекомендуется `max-size: 10m`, `max-file: 3`).

## Установка

```bash
sudo git clone https://github.com/sider1403-oss/tgwsproxy-panel.git /opt/tgws-panel
cd /opt/tgws-panel

sudo python3 -m venv venv
sudo venv/bin/pip install -r requirements.txt

cd frontend-src
sudo npm ci
sudo npm run build        # результат: /opt/tgws-panel/frontend
cd ..

# системные пользователи
sudo groupadd --system tgws-panel
sudo useradd --system --gid tgws-panel --home-dir /opt/tgws-panel \
  --no-create-home --shell /usr/sbin/nologin tgws-panel
sudo groupadd --system tgws-netmon
sudo useradd --system --gid tgws-netmon --home-dir /var/lib/tgws-panel-netmon \
  --no-create-home --shell /usr/sbin/nologin tgws-netmon

# каталоги и права
sudo install -d -o tgws-netmon -g tgws-netmon -m 700 /var/lib/tgws-panel-netmon
sudo chown -R tgws-panel:tgws-panel /opt/tgws-panel/data /opt/tgws-panel/logs /opt/tgws-panel/config
sudo chmod 700 /opt/tgws-panel/data /opt/tgws-panel/config
sudo chmod 750 /opt/tgws-panel/logs
sudo chmod 600 /opt/tgws-panel/data/panel.db* /opt/tgws-panel/logs/panel.log*
sudo chown -R root:root /opt/tgws-panel/backups /opt/tgws-panel/app /opt/tgws-panel/venv /opt/tgws-panel/frontend
sudo chmod 700 /opt/tgws-panel/backups

# units и CLI
sudo install -m 644 deploy/tgws-panel.service /etc/systemd/system/tgws-panel.service
sudo install -m 644 deploy/tgws-panel-helper.service /etc/systemd/system/tgws-panel-helper.service
sudo install -m 644 deploy/tgws-panel-netmon.service /etc/systemd/system/tgws-panel-netmon.service
sudo install -m 755 deploy/tgws-panel-admin /usr/local/bin/tgws-panel-admin
sudo install -m 600 deploy/panel.env.example /etc/tgws-panel.env
sudo nano /etc/tgws-panel.env      # укажите PANEL_PUBLIC_HOST и пути

sudo mkdir -p /etc/systemd/journald.conf.d
sudo install -m 644 deploy/99-tgws-panel.conf /etc/systemd/journald.conf.d/99-tgws-panel.conf
sudo systemctl restart systemd-journald

sudo systemctl daemon-reload
sudo systemctl enable --now tgws-panel-helper tgws-panel-netmon tgws-panel
sudo systemctl status tgws-panel-helper tgws-panel-netmon tgws-panel
```

Откройте `http://<PANEL_PUBLIC_HOST>:8090`.

### Первый вход

При первом запуске администратора ещё нет. Панель откроет страницу первоначальной настройки:

1. Придумайте логин (не `admin`/`root`/`administrator`/`user`/`guest`) и пароль
   (минимум 12 символов, буквы и цифры).
2. Нажмите «Создать администратора» — панель сразу войдёт под этой учётной записью.
3. После создания администратора страница настройки отключается.

Пароль задаёте вы; он сохраняется только как Argon2id-хеш. Панель не должна быть доступна
из интернета, пока администратор не создан.

Альтернатива — CLI (создаст администратора и потребует смены пароля при входе):

```bash
sudo tgws-panel-admin create-admin --username <login>
```

Восстановление доступа, если пароль потерян:

```bash
sudo tgws-panel-admin list-users
sudo tgws-panel-admin reset-password --username <login>
```

Сброс завершает все сессии и снимает блокировку после неудачных попыток. Повторно открыть
первичную настройку можно только на чистой БД (например, при переустановке панели) —
для действующей панели используйте `reset-password`.

Если Node.js на сервере нет, соберите фронтенд на машине разработчика
(`cd frontend-src && npm ci && npm run build`) и скопируйте каталог `frontend/` на сервер.

### Обновление

```bash
cd /opt/tgws-panel
sudo git pull
sudo venv/bin/pip install -r requirements.txt
cd frontend-src && sudo npm ci && sudo npm run build && cd ..
sudo install -m 644 deploy/tgws-panel.service /etc/systemd/system/tgws-panel.service
sudo install -m 644 deploy/tgws-panel-helper.service /etc/systemd/system/tgws-panel-helper.service
sudo install -m 644 deploy/tgws-panel-netmon.service /etc/systemd/system/tgws-panel-netmon.service
sudo install -m 755 deploy/tgws-panel-admin /usr/local/bin/tgws-panel-admin
sudo systemctl daemon-reload
sudo systemctl restart tgws-panel-helper tgws-panel-netmon tgws-panel
```

## Настройка

Переменные читаются из `/etc/tgws-panel.env` (systemd `EnvironmentFile`):

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `PANEL_PUBLIC_HOST` | `127.0.0.1` | IP/хост панели для ссылок в уведомлениях и TCP-проверок |
| `PANEL_PORT` | `8090` | Порт панели (должен совпадать с `--port` в unit) |
| `TGWS_PANEL_ROOT` | `/opt/tgws-panel` | Каталог панели (данные, логи, бэкапы) |
| `TGWS_PROXY_DIR` | `/opt/tg-ws-proxy` | Каталог compose-проекта прокси |
| `TGWS_CONTAINER` | `tgwsproxy` | Имя контейнера |
| `TGWS_SERVICE` | `tgwsproxy` | Имя сервиса в compose |
| `TGWS_PROXY_PORT` | `1443` | Порт прокси |
| `TGWS_SNIFF_IFACE` | `eth0` | Интерфейс для TCP SYN fingerprint |
| `SESSION_IDLE_MINUTES` | `60` | Завершение сессии после неактивности |
| `SESSION_ABSOLUTE_HOURS` | `12` | Максимальный срок жизни сессии |
| `PANEL_TRUSTED_PROXIES` | пусто | IP/CIDR reverse proxy, которым доверяются `X-Forwarded-*` |
| `PANEL_ALLOWED_ORIGINS` | пусто | Доп. Origin для CSRF (например, `https://panel.example.com`) |

`PANEL_TRUSTED_PROXIES` должен содержать **только** адрес вашего reverse proxy. Без него
заголовки `X-Forwarded-For`/`X-Forwarded-Proto` от клиентов игнорируются.

`PANEL_PORT` используется в ссылках/проверках; чтобы сменить фактический порт, измените
`--port` в `deploy/tgws-panel.service` и `PANEL_PORT` в env-файле.

## Ссылки LAN и интернет

Для каждого ключа панель показывает две ссылки `tg://proxy`:

- **LAN** — с адресом `PANEL_PUBLIC_HOST` (например, `192.168.50.5`): для устройств в
  локальной сети.
- **Интернет** — с публичным адресом (`TG_LINK_IP`): для внешних клиентов.

Это важно для корректных IP и определения устройств: если LAN-клиент подключается по
публичному IP через роутер, hairpin NAT может заменить источник на адрес шлюза
(например, `192.168.50.1`), и прокси уже не сможет узнать реальный IP телефона.
Для устройств дома используйте LAN-ссылку.

## Безопасность

- **Один администратор**, публичной регистрации нет. Пароль хранится только как **Argon2id**-хеш.
- Первичный администратор создаётся на странице настройки (логин и пароль задаёт сам
  администратор) или через CLI `tgws-panel-admin create-admin`; логины
  `admin`/`root`/`administrator` запрещены.
- **Серверные сессии** в SQLite: в cookie `tgws_session` лежит случайный токен
  (`HttpOnly`, `SameSite=Lax`, `Secure` при HTTPS). В БД хранится только SHA-256 токена.
  Сессия завершается по неактивности (`SESSION_IDLE_MINUTES`) и по абсолютному сроку
  (`SESSION_ABSOLUTE_HOURS`).
- Все `/api/*`, кроме `auth/status`, `auth/login`, `auth/setup` и минимального `/api/health`,
  требуют сессию. Изменяющие запросы требуют CSRF-токен и разрешённый Origin/Referer.
- После 5 неудачных попыток логин/пара блокируются на 15 минут; попытки логируются.
  Смена пароля завершает остальные сессии, выход удаляет сессию на сервере.
- **Ключи не отдаются списком**: `/api/keys` возвращает маску и `id`; полный ключ/ссылки
  доступны только через `POST /api/keys/{id}/reveal` с подтверждением текущего пароля.
- **Резервные копии** (каталог `700`, файлы `600`) скачиваются только после подтверждения
  пароля; архив содержит `.env` с TG_SECRET.
- Отдельный **журнал безопасности** фиксирует входы, выходы, смену пароля, сессии,
  CSRF-отказы, доступ без авторизации и административные действия. Пароли, cookie и полные
  секреты в журнал не попадают.
- Панель работает от `tgws-panel` (без root, Docker Socket, `sudo` и группы `docker`);
  root-операции выполняет только helper с allowlist, SYN-сниффер — отдельный netmon
  с `CAP_NET_RAW`. Панель остаётся **только для LAN**: не открывайте 8090 в интернет.
  Для HTTPS поставьте reverse proxy и укажите его адрес в `PANEL_TRUSTED_PROXIES`,
  а домен — в `PANEL_ALLOWED_ORIGINS`.
- Токен Telegram-бота хранится в `/opt/tgws-panel/config/alerts.json` (каталог `700`, файл `600`)
  и маскируется в API.

## Ограничения

- У `tg-ws-proxy` нет HTTP API: управление идёт через helper (Docker/`compose`), конфиг и логи.
- **Раздельная статистика по ключам невозможна**: прокси не пишет, каким секретом
  авторизовался клиент; MTProto-полезная нагрузка зашифрована.
- **Устройство клиента** определяется приблизительно по TCP SYN: iOS и macOS неразличимы,
  Android и Linux могут путаться; точный тип задаётся вручную для IP.
- Принудительный разрыв — TCP RST через `ss -K` в network namespace контейнера, а не API прокси.
- История ограничена ротацией Docker-логов и retention в SQLite (7 дней события/сэмплы,
  90 дней сессии, 30 дней аудит).
- Активные сессии не знают ключ и DC до завершения сессии.
- Нет 2FA/SSO и веб-управления несколькими пользователями: один администратор,
  дополнительные учётные записи — через CLI. Восстановление доступа требует SSH/root.
- `/api/health` остаётся публичным (только `{ok, ts}`) для мониторинга.
- Защита от подбора хранится в SQLite и рассчитана на один экземпляр панели, не на кластер.

## API

```
GET  /api/overview?range=1h
GET  /api/connections/active
GET  /api/connections/history
GET  /api/clients?range=24h&q=&active=&sort=&order=&limit=50&offset=0
GET  /api/clients/{ip}?range=7d
GET  /api/metrics/history?range=1h&fields=cpu_host,cpu_proxy&step=60
GET  /api/keys                   # маска, id, без секрета
POST /api/keys/{id}/reveal       # полный ключ после пароля
GET  /api/logs
GET  /api/diagnostics
POST /api/diagnostics/check
# POST /api/diagnostics/probe отключён (403): временные контейнеры запрещены
GET  /api/alerts
GET  /api/audit
GET  /api/storage
POST /api/service/action
GET/PUT /api/config
GET  /api/logs/stream        # SSE
GET  /api/stream?range=1h    # SSE
```

`/api/clients` агрегирует **завершённые** сессии по IP; `active=1` оставляет только
IP с текущими TCP-соединениями. `/api/clients/{ip}` возвращает сводку, DC, последние
сессии и активные TCP. `/api/metrics/history` отдаёт сэмплы `samples` (CPU, RAM,
скорости, соединения) с downsampling; `mem_total` в истории отсутствует — только в
текущем `/api/overview`. Ключ MTProto и DC активной сессии прокси не сообщает.

Аутентификация:

```
GET  /api/auth/status
POST /api/auth/login
POST /api/auth/setup
POST /api/auth/logout
POST /api/auth/password
GET  /api/security/overview
GET  /api/security/sessions
DELETE /api/security/sessions/{id}
POST /api/security/sessions/revoke-others
POST /api/security/sessions/revoke-all
GET  /api/security/events
GET  /api/security/attempts
```

## Разработка

Backend:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
TGWS_PANEL_ROOT="$PWD" PANEL_PUBLIC_HOST=127.0.0.1 \
  uvicorn app.main:app --reload --port 8090 --app-dir .
```

Frontend (Vite проксирует `/api` на `127.0.0.1:8090`):

```bash
cd frontend-src
npm install
npm run dev
```

CI (`.github/workflows/ci.yml`) проверяет компиляцию Python и сборку фронтенда.

## Ветки и разработка

- `main` — **только публикация** стабильных релизов; напрямую не коммитить.
- `develop` — текущая ветка разработки и улучшений.
- `fix` — исправления багов (PR в `develop`).
- `feature/<name>` — новая функциональность (PR в `develop`).
- `release/<version>` — подготовка публикации (PR в `main`, затем обратно в `develop`).

Подробный процесс — в [CONTRIBUTING.md](CONTRIBUTING.md), история версий — в
[CHANGELOG.md](CHANGELOG.md).

## Лицензия

MIT — см. [LICENSE](LICENSE).
