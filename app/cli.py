"""
Account recovery from the server, for when the admin is locked out or a
fresh install has no admin yet. Run inside the API container:

    docker exec -it database_manager_api python -m app.cli list
    docker exec -it database_manager_api python -m app.cli reset-password dad
    docker exec -it database_manager_api python -m app.cli set-role dad admin
    docker exec -it database_manager_api python -m app.cli activate grandad
    docker exec -it database_manager_api python -m app.cli create-user \
        dad "Dad" admin
"""
import argparse
import getpass
import sys
from app.database.database import SessionLocal
from app.models.user_models import User
# Importing these registers them on SQLAlchemy's mapper registry, which
# User's relationships need (mirrors what app.main does)
from app.models import (photo_model, message_model, shares_models,  # noqa
                        utilities, deductions_models)
from app.core.auth import hash_pw, ALL_ROLES, STATUS_ACTIVE


def _ask_password() -> str:
    password = getpass.getpass("New password: ")
    if not password or password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords were empty or did not match")
    return password


def _find(db, username: str) -> User:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        sys.exit(f"No user with username '{username}'")
    return user


def list_users(db, args):
    for user in db.query(User).order_by(User.id).all():
        print(f"{user.id:>3}  {user.username:<20} {user.role:<8} "
              f"{user.status}")


def reset_password(db, args):
    user = _find(db, args.username)
    user.hashed_password = hash_pw(args.password or _ask_password())
    db.commit()
    print(f"Password reset for {user.username}")


def set_role(db, args):
    user = _find(db, args.username)
    user.role = args.role
    db.commit()
    print(f"{user.username} is now {user.role}")


def activate(db, args):
    user = _find(db, args.username)
    user.status = STATUS_ACTIVE
    db.commit()
    print(f"{user.username} is now active")


def create_user(db, args):
    if db.query(User).filter(User.username == args.username).first():
        sys.exit(f"Username '{args.username}' already taken")
    db.add(User(username=args.username,
                display_name=args.display_name,
                role=args.role,
                status=STATUS_ACTIVE,
                hashed_password=hash_pw(args.password or _ask_password())))
    db.commit()
    print(f"Created {args.username} as {args.role}")


def build_parser():
    parser = argparse.ArgumentParser(prog="python -m app.cli",
                                     description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("list").set_defaults(func=list_users)

    reset = commands.add_parser("reset-password")
    reset.add_argument("username")
    reset.add_argument("--password", help="omit to be prompted")
    reset.set_defaults(func=reset_password)

    role = commands.add_parser("set-role")
    role.add_argument("username")
    role.add_argument("role", choices=ALL_ROLES)
    role.set_defaults(func=set_role)

    active = commands.add_parser("activate")
    active.add_argument("username")
    active.set_defaults(func=activate)

    create = commands.add_parser("create-user")
    create.add_argument("username")
    create.add_argument("display_name")
    create.add_argument("role", choices=ALL_ROLES)
    create.add_argument("--password", help="omit to be prompted")
    create.set_defaults(func=create_user)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    db = SessionLocal()
    try:
        args.func(db, args)
    finally:
        db.close()


if __name__ == "__main__":
    main()
