# Участие в разработке

## Модель веток

| Ветка | Назначение | Откуда | Куда мержить |
|---|---|---|---|
| `main` | Стабильные релизы и деплой | — | — |
| `develop` | Интеграция разработки | `main` | `main` через release/PR |
| `fix` | Постоянная ветка исправления багов | `main` | `main`, затем `main` → `develop` |
| `feature/<name>` | Новая функциональность | `develop` | `develop` |
| `release/<version>` | Подготовка релиза | `develop` | `main`, затем обратно в `develop` |

`main` и `develop` должны быть защищены в GitHub: PR, зелёный CI, запрет force-push.
`feature/*` и `release/*` — короткоживущие, удаляются после merge. Ветка `fix` постоянная:
после каждого исправления синхронизируйте её с `main`.

## Исправление бага

```bash
git checkout fix
git pull

# правки, проверка
git add -A
git commit -m "Fix: short description"
git push
```

Откройте PR `fix` → `main`. После merge синхронизируйте ветки:

```bash
git checkout develop
git pull
git merge main
git push

git checkout fix
git merge main
git push
```

## Новая функциональность

```bash
git checkout develop
git pull
git checkout -b feature/short-description

git add -A
git commit -m "Feature: short description"
git push -u origin feature/short-description
```

PR в `develop`. После merge ветку удалить.

## Релиз

```bash
git checkout develop
git pull
git checkout -b release/1.2.0

# обновить CHANGELOG.md, при необходимости версию в коде
git commit -am "Release 1.2.0"
git push -u origin release/1.2.0
```

PR `release/1.2.0` → `main`, затем:

```bash
git checkout main
git pull
git tag -a v1.2.0 -m "v1.2.0"
git push origin v1.2.0

git checkout develop
git merge main
git push
```

## Требования к PR

- CI зелёный (backend `compileall`, frontend `npm ci && npm run build`).
- Не коммитить `.env`, `data/`, `logs/`, `backups/`, `config/alerts.json`, токены и ключи.
- Для изменений конфигурации/ключей — проверить сценарий отката.
- В описании PR: что изменено, как проверено, влияние на прокси.

## Версии

SemVer: `vMAJOR.MINOR.PATCH`.
- `main` — только стабильные теги.
- `develop` — допускаются pre-release теги (`v1.2.0-rc.1`).
- `CHANGELOG.md` обновляется в release-ветке.
