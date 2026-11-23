# tgwsproxy-panel

[![CI](https://github.com/sider1403-oss/tgwsproxy-panel/actions/workflows/ci.yml/badge.svg)](https://github.com/sider1403-oss/tgwsproxy-panel/actions/workflows/ci.yml)

Веб-панель администрирования для уже работающего
[Telegram WebSocket Proxy](https://github.com/valnesfjord/tg-ws-proxy-rs)
(`tg-ws-proxy-rs`, контейнер `tgwsproxy`) на базе Docker Compose.

Панель не устанавливает второй прокси и не меняет его архитектуру: она управляет существующим
контейнером через `docker compose`, читает его журнал и конфигурацию, показывает сетевые сокеты
и пассивно определяет семейство устройства клиента.

> Проверено с `tg-ws-proxy 2.7.2` (образ `valnesfjord/tg-ws-proxy-rs`).
> Панель рассчитана на доверенную локальную сеть: авторизации нет.

## Возможности

- **Дашборд** — статус и health, uptime, версия, активные сессии, клиенты, трафик в обе стороны,
  скорость, ошибки/предупреждения, CPU/RAM LXC и контейнера, графики трафика и подключений,
  распределение по DC.
- **Подключения** — активные TCP-сессии (IP, устройство, порт, длительность, TCP-счётчики,
  принудительный разрыв) и история из журнала с поиском, фильтрами, сортировкой и пагинацией.
- **Устройства** — приблизительное определение по TCP SYN (Windows, Apple/iOS/macOS, Android,
  Linux) с иконками и возможностью указать точный тип вручную для IP.
- **Ключи** — реальные ключи из `TG_SECRET`: показ, копирование `tg://`, создание,
  отключение/включение, удаление, комментарии. Для каждого ключа — отдельная LAN-ссылка
  и ссылка для внешних клиентов (см. ниже).
- **Логи** — уровни INFO/WARN/ERROR/DEBUG, категории, поиск, период, live-поток (SSE),
  детали, экспорт TXT/CSV, маскирование секретов.
- **Сервис** — запуск/остановка/перезапуск через `docker compose`, проверка порта,
  `docker logs`, действующая конфигурация, журнал действий администратора.
- **Диагностика** — быстрые проверки канала и сквозная MTProto-проба через временный
  контейнер без публикации порта; история проверок.
- **Уведомления** — Telegram-бот и/или webhook, правила, антидребезг, тест, история доставки.
- **Конфигурация** — просмотр и редактирование известных `TG_*` и `--dc-ip`, валидация,
  автоматический бэкап, применение с откатом, восстановление копий.
- **Тема** — тёмная по умолчанию, светлая по кнопке; выбор сохраняется в браузере.
- **Лимиты** — ограничены `panel.log`, journald, Docker-лог, БД (retention + мягкий лимит),
  резервные копии; в UI есть карточка «Хранилище и лимиты логов».

## Архитектура

```
Браузер ──HTTP/SSE──> FastAPI (uvicorn, :8090, root)
                          │
                          ├── docker inspect / docker compose ──> tgwsproxy
                          ├── docker logs (json-file) ──> SQLite (data/panel.db)
                          ├── nsenter + ss ──> активные сокеты и RST
                          ├── /proc, cgroup ──> CPU/RAM/сеть
                          └── AF_PACKET ──> TCP SYN fingerprint (устройства)

React SPA (Vite) ── статика из frontend/
```

Backend работает одним процессом, слушает `0.0.0.0:8090` и запускается от root:
ему нужны Docker CLI, `nsenter` и raw-socket для пассивного определения устройств.

## Требования

- Linux (проверено на Debian 12 / LXC), root.
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

sudo install -m 644 deploy/tgws-panel.service /etc/systemd/system/tgws-panel.service
sudo install -m 600 deploy/panel.env.example /etc/tgws-panel.env
sudo nano /etc/tgws-panel.env      # укажите PANEL_PUBLIC_HOST и пути

sudo mkdir -p /etc/systemd/journald.conf.d
sudo install -m 644 deploy/99-tgws-panel.conf /etc/systemd/journald.conf.d/99-tgws-panel.conf
sudo systemctl restart systemd-journald

sudo systemctl daemon-reload
sudo systemctl enable --now tgws-panel
sudo systemctl status tgws-panel
```

Откройте `http://<PANEL_PUBLIC_HOST>:8090`.

Если Node.js на сервере нет, соберите фронтенд на машине разработчика
(`cd frontend-src && npm ci && npm run build`) и скопируйте каталог `frontend/` на сервер.

### Обновление

```bash
cd /opt/tgws-panel
sudo git pull
sudo venv/bin/pip install -r requirements.txt
cd frontend-src && sudo npm ci && sudo npm run build && cd ..
sudo systemctl restart tgws-panel
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

- Панель **без встроенной авторизации** и работает от root: доступ к порту 8090 равносилен
  доступу к Docker на сервере. Держите её только в доверенной LAN, не делайте port-forward.
- Для удалённого доступа используйте SSH-туннель или поставьте reverse proxy с авторизацией.
- Токен Telegram-бота хранится в `/opt/tgws-panel/config/alerts.json` (каталог `700`, файл `600`)
  и маскируется в API.
- Панель не изменяет неизвестные параметры compose и не хранит секрет прокси в репозитории.

## Ограничения

- У `tg-ws-proxy` нет HTTP API: управление идёт через `docker compose`, конфиг и логи.
- **Раздельная статистика по ключам невозможна**: прокси не пишет, каким секретом
  авторизовался клиент; MTProto-полезная нагрузка зашифрована.
- **Устройство клиента** определяется приблизительно по TCP SYN: iOS и macOS неразличимы,
  Android и Linux могут путаться; точный тип задаётся вручную для IP.
- Принудительный разрыв — TCP RST через `ss -K` в network namespace контейнера, а не API прокси.
- История ограничена ротацией Docker-логов и retention в SQLite (7 дней события/сэмплы,
  90 дней сессии, 30 дней аудит).
- Активные сессии не знают ключ и DC до завершения сессии.

## API

```
GET  /api/overview?range=1h
GET  /api/connections/active
GET  /api/connections/history
GET  /api/keys
GET  /api/logs
GET  /api/diagnostics
POST /api/diagnostics/check
POST /api/diagnostics/probe
GET  /api/alerts
GET  /api/audit
GET  /api/storage
POST /api/service/action
GET/PUT /api/config
GET  /api/logs/stream        # SSE
GET  /api/stream?range=1h    # SSE
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

- `main` — стабильные релизы и деплой.
- `develop` — интеграция разработки.
- `fix` — постоянная ветка исправлений багов (PR в `main`, затем merge в `develop`).
- `feature/<name>` — новая функциональность (PR в `develop`).
- `release/<version>` — подготовка релиза (PR в `main`, затем обратно в `develop`).

Подробный процесс — в [CONTRIBUTING.md](CONTRIBUTING.md), история версий — в
[CHANGELOG.md](CHANGELOG.md).

## Лицензия

MIT — см. [LICENSE](LICENSE).
