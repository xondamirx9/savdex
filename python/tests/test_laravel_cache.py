"""Сброс кэша Laravel из Django — без базы: путь файла и отказ без исключения."""

from __future__ import annotations

import hashlib

from savdex import laravel_cache


def test_путь_файла_как_у_filestore(settings, tmp_path):
    """FileStore::path(): data/<первые два знака sha1>/<следующие два>/<sha1>."""
    settings.LARAVEL_ROOT = tmp_path
    digest = hashlib.sha1(b"settings.all").hexdigest()

    assert laravel_cache.file_path("settings.all") == (
        tmp_path / "storage/framework/cache/data" / digest[:2] / digest[2:4] / digest
    )


def test_файл_удаляется(settings, tmp_path, monkeypatch):
    settings.LARAVEL_ROOT = tmp_path
    monkeypatch.setenv("CACHE_STORE", "file")
    path = laravel_cache.file_path("settings.all")
    path.parent.mkdir(parents=True)
    path.write_text("x")

    assert laravel_cache.forget("settings.all") is True
    assert not path.exists()
    # Второй раз — файла уже нет, и это не ошибка
    assert laravel_cache.forget("settings.all") is True


def test_неудача_не_роняет_правку(settings, tmp_path, monkeypatch, caplog):
    """Файл не удалить (чужие права) — правка остаётся, неудача в логе."""
    settings.LARAVEL_ROOT = tmp_path
    monkeypatch.setenv("CACHE_STORE", "file")
    path = laravel_cache.file_path("settings.all")
    path.mkdir(parents=True)  # на месте файла — папка: unlink() бросит OSError

    assert laravel_cache.forget("settings.all") is False
    assert "не сброшен" in caplog.text


def test_кэш_в_памяти_сбрасывать_нечего(monkeypatch):
    monkeypatch.setenv("CACHE_STORE", "array")

    assert laravel_cache.forget("settings.all") is True
