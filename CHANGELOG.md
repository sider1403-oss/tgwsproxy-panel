# Changelog

Все заметные изменения проекта. Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версии — [SemVer](https://semver.org/lang/ru/).

## [Unreleased]

## [1.2.0] — 2026-11-25

### Added
- Интерактивный дашборд: карточки стали кликабельными и ведут в детали — `/service`, `/traffic`,
  `/connections?tab=active`, `/clients`, `/metrics/cpu`, `/logs?level=ERROR|WARN`; работают hover,
  focus-ring и переходы с клавиатуры.
- Новые разделы: «Клиенты» (`/clients`, `/clients/:id`), «Метрики» (`/metrics`), «Трафик» (`/traffic`),
  «DC» (`/dc`) с графиками, сводками и детализацией по диапазонам.
- API для аналитики (`clients`, `metrics`, `traffic`, `dc`) и индекс в БД для выборок по клиентам.
- `tgws-panel-helper.service`: root-helper с Unix-сокетом, `SO_PEERCRED` и allowlist операций
  (Docker только `tgwsproxy`, nsenter/ss, конфигурация, резервные копии, чтение Docker-логов).
- `tgws-panel-netmon.service`: AF_PACKET-сниффер SYN с `CAP_NET_RAW`.

### Changed
- Основной процесс переведён на системного пользователя `tgws-panel` без root, Docker Socket,
  `sudo` и группы `docker`.
- Docker/nsenter/конфигурация/бэкапы/логи вынесены в helper; SYN-сниффер — в netmon, без доступа
  к Docker, `.env` и базе панели.
- Панель, helper и netmon получили systemd-hardening (`ProtectSystem=strict`, `NoNewPrivileges`,
  `PrivateTmp`, `CapabilityBoundingSet`, `InaccessiblePaths` и др.).
- Резервные копии остаются root-only; скачивание идёт через helper после подтверждения пароля.
- Сквозная диагностическая проба с временным контейнером отключена.

### Fixed
- Активные подключения: вход в netns через Docker `SandboxKey`
  (`nsenter --net=/run/docker/netns/<id>`) без `CAP_SYS_PTRACE` — список соединений больше не пустой.

### Docs
- Команды сборки фронтенда для root-owned `frontend/`.

## [1.1.0] — 2026-11-23

### Added
- Авторизация администратора: Argon2id, серверные сессии в SQLite, cookie HttpOnly/SameSite,
  ограничение попыток входа, CSRF и проверка Origin/Referer.
- Первоначальная настройка: администратор сам задаёт логин и пароль (без одноразового кода);
  CLI `tgws-panel-admin` (`create-admin`, `reset-password`, `list-users`, `disable-user`, `logout-all`).
- Раздел «Безопасность»: смена пароля, активные сессии, завершение сессий, журнал событий,
  последний вход и неудачные попытки. Принудительная смена временного пароля.
- Маскирование ключей в списке; полный `tg://` и ключ доступны только после подтверждения пароля.
- Защита резервных копий и прав файлов; скачивание архива конфигурации требует пароль.
- Принудительная смена пароля, завершение всех сессий и повторная проверка сессии в SSE.

### Changed
- Все административные API защищены сессией; `/api/health` остаётся публичным.
- `--proxy-headers` убран из unit: доверенные `X-Forwarded-*` задаются явно через env.

## [1.0.1] — 2026-11-23

### Added
- Отдельные `tg://`-ссылки для LAN и внешних клиентов; предупреждение о hairpin NAT,
  из-за которого IP клиента может подменяться адресом шлюза.

### Fixed
- Копирование ссылки по умолчанию для устройств в локальной сети.

## [1.0.0] — 2026-11-23

### Added
- Дашборд, подключения с определением устройств, ключи, логи, диагностика, уведомления,
  аудит, управление сервисом и конфигурацией, лимиты логов и БД.
- Тёмная и светлая темы, SSE, systemd-развёртывание, CI.
