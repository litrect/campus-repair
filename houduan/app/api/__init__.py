from flask import Blueprint

api = Blueprint('api', __name__, url_prefix='/api')

from . import health  # noqa: E402,F401
from . import login  # noqa: E402,F401
from . import orders  # noqa: E402,F401
from . import workflow  # noqa: E402,F401
from . import reports  # noqa: E402,F401
