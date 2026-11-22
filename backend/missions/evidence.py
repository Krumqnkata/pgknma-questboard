"""
Проверка и подготовка на файловете към доказателство (снимки и PDF).

Защо така:
  - Не вярваме на разширението и на типа, които казва браузърът – гледаме
    самото съдържание. Снимката трябва да се отвори от Pillow, а PDF-ът да
    започва с „%PDF-“. Всичко друго се отказва.
  - Всяка снимка се записва наново като JPEG, най-много 1600 px. Така:
      * махат се скритите данни (EXIF), например GPS мястото, където е
        направена снимката – важно е, защото учениците са непълнолетни;
      * файлът става малък, а сървърът не пази огромни снимки от телефон;
      * ако във файла е скрито нещо друго, то не оцелява.
  - Видео не се качва (бързо пълни диска) – слага се като връзка в текста.
Ограниченията (брой файлове и MB) са в „Настройки на играта“ → „Доказателства“.
"""
from dataclasses import dataclass
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

from .errors import GameRuleError

MAX_SIDE = 1600              # най-голямата страна на записаната снимка
MAX_PIXELS = 40_000_000      # по-голяма снимка не се отваря (защита от „декомпресионна бомба“)
IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}
ACCEPT = "image/jpeg,image/png,image/webp,image/gif,application/pdf"


@dataclass
class PreparedFile:
    content: ContentFile
    kind: str          # "image" или "pdf"
    original_name: str


def _short_name(name):
    name = (name or "файл").replace("\\", "/").rsplit("/", 1)[-1]
    return name[:150]


def prepare(upload, max_bytes):
    """Проверява един качен файл и връща готовото за запис съдържание или хвърля GameRuleError."""
    name = _short_name(getattr(upload, "name", ""))
    if upload.size > max_bytes:
        raise GameRuleError(f"„{name}“ е по-голям от {max_bytes // (1024 * 1024)} MB.")

    head = upload.read(5)
    upload.seek(0)
    if head == b"%PDF-":
        return PreparedFile(ContentFile(upload.read()), "pdf", name)

    try:
        with Image.open(upload) as image:
            if image.format not in IMAGE_FORMATS:
                raise UnidentifiedImageError
            if image.width * image.height > MAX_PIXELS:
                raise GameRuleError(f"„{name}“ е твърде голяма снимка.")
            image.load()
            picture = ImageOps.exif_transpose(image)  # завърта я правилно, преди да махнем EXIF
            picture.thumbnail((MAX_SIDE, MAX_SIDE))
            if picture.mode in ("RGBA", "LA", "P"):
                picture = picture.convert("RGBA")
                background = Image.new("RGB", picture.size, (255, 255, 255))
                background.paste(picture, mask=picture.getchannel("A"))
                picture = background
            elif picture.mode != "RGB":
                picture = picture.convert("RGB")
            output = BytesIO()
            picture.save(output, "JPEG", quality=85, optimize=True)  # без EXIF
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError):
        raise GameRuleError(f"„{name}“ не е снимка (JPG, PNG, WebP) или PDF.")
    return PreparedFile(ContentFile(output.getvalue()), "image", name)


def prepare_all(uploads, rules):
    """Проверява всички файлове преди да се запише каквото и да е."""
    uploads = [upload for upload in uploads if upload]
    if not uploads:
        return []
    if not rules.evidence_max_files:
        raise GameRuleError("Прикачването на файлове е изключено от администратора.")
    if len(uploads) > rules.evidence_max_files:
        raise GameRuleError(f"Най-много {rules.evidence_max_files} файла към една заявка.")
    return [prepare(upload, rules.evidence_max_mb * 1024 * 1024) for upload in uploads]
