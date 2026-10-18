from ..db import get_db
from ..repositories.health_repository import ping


def check_database():
    return ping(get_db())
