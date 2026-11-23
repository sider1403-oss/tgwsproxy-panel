"""CLI for panel administrators.

Usage:
    python -m app.cli create-admin --username admin
    python -m app.cli reset-password --username admin
    python -m app.cli list-users
    python -m app.cli disable-user --username admin
    python -m app.cli enable-user --username admin
    python -m app.cli logout-all --username admin
"""
from __future__ import annotations

import argparse
import getpass
import sys

from . import db, security


def _read_password(confirm: bool = True) -> str:
    password = getpass.getpass("Пароль: ")
    if confirm:
        again = getpass.getpass("Повторите пароль: ")
        if password != again:
            raise SystemExit("Пароли не совпадают")
    return password


def _create(args) -> None:
    if security.user_count():
        raise SystemExit("Администратор уже создан. Используйте reset-password.")
    username = args.username.strip().lower()
    password = args.password or _read_password()
    try:
        user = security.create_admin(username, password, must_change=args.must_change)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    security.ensure_setup_state()
    print(f"Администратор создан: {user['username']}")
    if args.must_change:
        print("При первом входе потребуется сменить пароль.")


def _reset(args) -> None:
    user = security.get_user_by_username(args.username)
    if not user:
        raise SystemExit("Пользователь не найден")
    password = args.password or _read_password()
    try:
        security.set_password(user["id"], password)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    count = security.revoke_all_sessions(user["id"])
    db.execute("UPDATE users SET must_change_password=0 WHERE id=?", (user["id"],))
    security.log_event("password_reset_cli", username=user["username"], detail=f"revoked={count}")
    print(f"Пароль изменён: {user['username']}; завершено сессий: {count}")


def _list(_args) -> None:
    rows = db.query("SELECT id,username,is_active,is_admin,must_change_password,created_at,last_login_at FROM users ORDER BY id")
    if not rows:
        print("Пользователей нет. Панель ожидает первоначальную настройку.")
        return
    for row in rows:
        print(
            f"#{row['id']} {row['username']} active={bool(row['is_active'])} "
            f"admin={bool(row['is_admin'])} must_change={bool(row['must_change_password'])} "
            f"created={row['created_at']} last_login={row['last_login_at'] or '—'}"
        )


def _set_active(args, active: bool) -> None:
    user = security.get_user_by_username(args.username)
    if not user:
        raise SystemExit("Пользователь не найден")
    db.execute("UPDATE users SET is_active=? WHERE id=?", (1 if active else 0, user["id"]))
    if not active:
        security.revoke_all_sessions(user["id"])
    print(f"{user['username']}: {'включён' if active else 'отключён'}")


def _logout_all(args) -> None:
    user = security.get_user_by_username(args.username)
    if not user:
        raise SystemExit("Пользователь не найден")
    count = security.revoke_all_sessions(user["id"])
    print(f"Завершено сессий: {count}")


def main(argv: list[str] | None = None) -> None:
    db.conn()
    parser = argparse.ArgumentParser(description="TGWSProxy panel administration")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create-admin", help="создать первого администратора")
    p.add_argument("--username", required=True)
    p.add_argument("--password", help="небезопасно: пароль в аргументах; лучше без флага")
    p.add_argument("--must-change", action="store_true", help="потребовать смену пароля при первом входе")
    p.set_defaults(func=_create)

    p = sub.add_parser("reset-password", help="сбросить пароль и завершить все сессии")
    p.add_argument("--username", required=True)
    p.add_argument("--password", help="небезопасно: пароль в аргументах; лучше без флага")
    p.set_defaults(func=_reset)

    p = sub.add_parser("list-users", help="список пользователей")
    p.set_defaults(func=_list)

    p = sub.add_parser("disable-user", help="отключить пользователя и его сессии")
    p.add_argument("--username", required=True)
    p.set_defaults(func=lambda a: _set_active(a, False))

    p = sub.add_parser("enable-user", help="включить пользователя")
    p.add_argument("--username", required=True)
    p.set_defaults(func=lambda a: _set_active(a, True))

    p = sub.add_parser("logout-all", help="завершить все сессии пользователя")
    p.add_argument("--username", required=True)
    p.set_defaults(func=_logout_all)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
