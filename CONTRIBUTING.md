# Участие в разработке

## Модель веток

| Ветка | Назначение | Откуда | Куда мержить |
|---|---|---|---|
| `main` | **Только публикация** стабильных релизов | `release/*` | — |
| `develop` | Разработка и улучшения; текущая рабочая ветка | `main` | `release/*` |
| `fix` | Исправления багов | `develop` | `develop` |
| `feature/<name>` | Новая функциональность | `develop` | `develop` |
| `release/<version>` | Подготовка публикации | `develop` | `main`, затем обратно в `develop` |

`main` не используется для повседневной работы: в него попадают только проверенные релизы
через `release/*`. Вся разработка, улучшения и исправления ведутся в `develop`/`fix`.

`main` и `develop` должны быть защищены в GitHub: PR, зелёный CI, запрет force-push.
`feature/*` и `release/*` — короткоживущие. Ветка `fix` синхронизируется с `develop`
после каждого исправления.

## Исправление бага

```bash
git checkout develop
git pull
git checkout fix
git merge develop

# правки, проверка
git add -A
git commit -m "Fix: short description"
git push
```

Откройте PR `fix` → `develop`. Публикация исправления — позже через `release/*` → `main`.

## Новая функциональность / улучшение

```bash
git checkout develop
git pull
git checkout -b feature/short-description

git add -A
git commit -m "Feature: short description"
git push -u origin feature/short-description
```

PR в `develop`. После merge ветку удалить.

## Публикация релиза

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
