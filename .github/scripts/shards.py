"""
Файлы тестов для одного из N параллельных потоков CI (.github/workflows/python.yml).

  python shards.py <номер потока, с 1> <всего потоков> [папка тестов]

Печатает файлы потока через пробел. Раскладка — жадная по размеру файла
(больший файл — в самый лёгкий пока поток): размер грубо, но стабильно
повторяет длительность. Без случайности: один и тот же набор файлов —
одна и та же раскладка, и каждый файл попадает ровно в один поток.
"""

from __future__ import annotations

import sys
from pathlib import Path


def shards(files: list[Path], total: int) -> list[list[Path]]:
    loads = [0] * total
    groups: list[list[Path]] = [[] for _ in range(total)]

    for path in sorted(files, key=lambda p: (-p.stat().st_size, p.name)):
        lightest = loads.index(min(loads))
        groups[lightest].append(path)
        loads[lightest] += path.stat().st_size

    return groups


def main() -> None:
    index, total = int(sys.argv[1]), int(sys.argv[2])
    directory = Path(sys.argv[3] if len(sys.argv) > 3 else "tests")

    if not 1 <= index <= total:
        sys.exit(f"Поток {index} из {total}: нужен номер от 1 до {total}")

    files = sorted(directory.glob("test_*.py"))
    if not files:
        sys.exit(f"В {directory} нет файлов test_*.py")

    print(" ".join(str(p) for p in sorted(shards(files, total)[index - 1])))


if __name__ == "__main__":
    main()
