import fcntl

from alembic import command
from alembic.config import Config

from .config import ROOT, get_settings


def migrate():
    directory = get_settings().data_dir
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".migration.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        config = Config(str(ROOT / "backend" / "alembic.ini"))
        config.set_main_option("script_location", str(ROOT / "backend" / "migrations"))
        command.upgrade(config, "head")


if __name__ == "__main__":
    migrate()
