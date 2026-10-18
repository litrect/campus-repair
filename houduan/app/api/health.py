from . import api
from ..responses import success
from ..services.health_service import check_database


@api.get('/health')
def health():
    return success({'status': 'ok'})


@api.get('/health/ready')
def ready():
    check_database()
    return success({'status': 'ready'})
