from rq import SpawnWorker

from .jobs import QUEUE, connection
from .migrate import migrate

if __name__ == "__main__":
    migrate()
    SpawnWorker([QUEUE], connection=connection(), serializer="json").work(logging_level="WARNING")
