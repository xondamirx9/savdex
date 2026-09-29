"""
Тип загруженного файла по содержимому — как у Laravel.

UploadedFile::guessExtension берёт тип у finfo (libmagic внутри PHP), а
расширение — первым из карты Symfony Mime для этого типа. Здесь тот же
libmagic через ctypes (системная libmagic.so.1; в образе — пакет
libmagic1) и выдержка из карты Symfony: типы, среди расширений которых
есть хоть одно из тех, что разрешают правила mimes площадки. Для прочих
типов расширение не нужно: правило mimes их всё равно отвергнет.

Без libmagic (машина разработчика без пакета) тип угадывается по первым
байтам — только картинки и PDF.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import threading
from functools import cache

#: MimeTypes::MAP Symfony: тип → первое расширение (выдержка, см. выше)
EXTENSIONS = {
    "application/acrobat": "pdf",
    "application/msexcel": "xls",
    "application/mspowerpoint": "ppz",
    "application/msword": "doc",
    "application/nappdf": "pdf",
    "application/pdf": "pdf",
    "application/powerpoint": "ppz",
    "application/vnd.ms-excel": "xls",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.ms-word": "doc",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/x-msexcel": "xls",
    "application/x-mspowerpoint": "ppz",
    "application/x-msword": "doc",
    "application/x-pdf": "pdf",
    "application/x-zip": "zip",
    "application/x-zip-compressed": "zip",
    "application/zip": "zip",
    "image/apng": "apng",
    "image/gif": "gif",
    "image/jpeg": "jpg",
    "image/pdf": "pdf",
    "image/pjpeg": "jpg",
    "image/png": "png",
    "image/vnd.mozilla.apng": "apng",
    "image/webp": "webp",
    "text/plain": "txt",
    "zz-application/zz-winassoc-doc": "doc",
    "zz-application/zz-winassoc-xls": "xls",
}

#: magic.h: MAGIC_MIME_TYPE — только тип, без кодировки (FILEINFO_MIME_TYPE)
_MAGIC_MIME_TYPE = 0x10

_lock = threading.Lock()


class _Magic:
    """Открытый libmagic с загруженной базой; вызовы — под замком."""

    def __init__(self, lib: ctypes.CDLL) -> None:
        lib.magic_open.restype = ctypes.c_void_p
        lib.magic_open.argtypes = [ctypes.c_int]
        lib.magic_load.restype = ctypes.c_int
        lib.magic_load.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        lib.magic_buffer.restype = ctypes.c_char_p
        lib.magic_buffer.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
        self.lib = lib
        self.cookie = lib.magic_open(_MAGIC_MIME_TYPE)

        if not self.cookie or lib.magic_load(self.cookie, None) != 0:
            raise OSError("libmagic: база типов не загрузилась")

    def mime(self, data: bytes) -> str | None:
        with _lock:
            found = self.lib.magic_buffer(self.cookie, data, len(data))

        return found.decode("ascii", "replace") if found else None


@cache
def _magic() -> _Magic | None:
    name = ctypes.util.find_library("magic") or "libmagic.so.1"

    try:
        return _Magic(ctypes.CDLL(name))
    except OSError:
        return None


def _sniff(head: bytes) -> str | None:
    """Запас без libmagic: картинки и PDF по первым байтам."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"

    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"

    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"

    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"

    if head.startswith(b"%PDF-"):
        return "application/pdf"

    return None


def mime_type(data: bytes) -> str | None:
    """finfo(FILEINFO_MIME_TYPE)->file(): тип по содержимому."""
    magic = _magic()

    return magic.mime(data) if magic is not None else _sniff(data[:64])


def guess_extension(data: bytes) -> str | None:
    """UploadedFile::guessExtension: первое расширение типа по карте Symfony."""
    mime = mime_type(data)

    return None if mime is None else EXTENSIONS.get(mime)
