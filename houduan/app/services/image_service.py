from io import BytesIO
from pathlib import Path
import re
import uuid
import warnings

from flask import current_app
from PIL import Image, UnidentifiedImageError

from ..db import get_db
from ..errors import BusinessError
from ..repositories.order_repository import worker_can_read_image
from ..validation import positive_id

IMAGE_URL = re.compile(r'/api/uploads/images/([1-9][0-9]{0,18})/([0-9a-f]{32}\.(?:png|jpg))')


def image_path(student_id, filename):
    root = Path(current_app.config['UPLOAD_FOLDER']).resolve()
    directory = root / str(student_id)
    path = directory / filename
    if directory.is_symlink() or path.is_symlink() or path.resolve().parent != directory:
        raise BusinessError('图片地址不合法', 400)
    return path


def validate_reference(image_url, student_id):
    if image_url is None:
        return None
    match = IMAGE_URL.fullmatch(image_url) if isinstance(image_url, str) else None
    if not match or positive_id(match[1]) != student_id:
        raise BusinessError('只能使用本人上传的有效图片', 400)
    path = image_path(student_id, match[2])
    if not path.is_file():
        raise BusinessError('图片不存在，请重新上传', 400)
    return image_url


def upload_image(file, student_id):
    content = file.stream.read(current_app.config['IMAGE_MAX_BYTES'] + 1)
    if len(content) > current_app.config['IMAGE_MAX_BYTES']:
        raise BusinessError('图片不能超过 2 MiB', 413)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                extension = {'PNG': 'png', 'JPEG': 'jpg'}.get(image.format)
                if extension is None:
                    raise BusinessError('仅支持 PNG/JPEG 图片', 400)
                image.verify()
            with Image.open(BytesIO(content)) as image:
                image.load()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError,
            Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise BusinessError('图片内容无效，仅支持 PNG/JPEG', 400) from None
    filename = f'{uuid.uuid4().hex}.{extension}'
    path = image_path(student_id, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as destination:
        destination.write(content)
    return f'/api/uploads/images/{student_id}/{filename}'


def readable_image(student_id, filename, actor):
    url = f'/api/uploads/images/{student_id}/{filename}'
    match = IMAGE_URL.fullmatch(url)
    if match is None:
        raise BusinessError('资源不存在或不可访问', 404)
    student_id = positive_id(student_id)
    allowed = actor['role'] == 'ADMIN' or (actor['role'] == 'STUDENT' and actor['id'] == student_id)
    if not allowed and actor['role'] == 'WORKER':
        allowed = worker_can_read_image(get_db(), url, actor['id'])
    if not allowed:
        raise BusinessError('资源不存在或不可访问', 404)
    path = image_path(student_id, filename)
    if not path.is_file():
        raise BusinessError('资源不存在或不可访问', 404)
    return path
