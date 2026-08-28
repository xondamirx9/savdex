<?php

declare(strict_types=1);

namespace App\Support;

use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Str;
use League\Flysystem\FilesystemException;
use RuntimeException;

/**
 * Приём и обработка изображений: логотипы компаний, фото объявлений.
 *
 * Своё на GD, а не пакет: нужны ровно две операции — вписать в рамку
 * и сжать в WebP. Тянуть ради этого зависимость с полусотней классов
 * и своим слоем абстракции над драйверами не за что.
 *
 * Что здесь важно и почему:
 *
 * Файл пересобирается, а не сохраняется как есть. Изображение с камеры
 * весит 6 МБ и грузится на мобильном интернете десяток секунд; в каталоге
 * таких двадцать штук на страницу. Плюс пересборка убивает полезную
 * нагрузку, спрятанную в EXIF или в хвосте файла: наружу выходит только
 * то, что GD смог прочитать как пиксели.
 *
 * WebP — потому что он есть в GD этой сборки и весит вдвое меньше JPEG
 * при том же качестве. Браузеры без поддержки WebP на рынке не остались.
 */
class ImageStore
{
    /** Что принимаем на вход. HEIC не берём: GD его не читает. */
    public const ALLOWED_MIMES = ['jpg', 'jpeg', 'png', 'webp'];

    public const MAX_SIZE_KB = 8192;

    /**
     * Потолок площади в пикселях (48 Мп ≈ 8000×6000).
     *
     * Ограничение размера файла не спасает от «бомбы распаковки»: PNG
     * со сплошной заливкой весит килобайты, но 25000×25000 разворачивается
     * в пару гигабайт при декодировании. GD выделяет память до того, как
     * мы узнаём размеры, поэтому проверяем их по заголовку — заранее.
     */
    public const MAX_PIXELS = 48_000_000;

    /** Логотип: квадрат под плашку на визитке и в списках. */
    public const LOGO = ['w' => 512, 'h' => 512, 'quality' => 85];

    /** Фото объявления: длинная сторона под карточку товара. */
    public const PHOTO = ['w' => 1600, 'h' => 1600, 'quality' => 82];

    /** Уменьшенная копия для списков — грузить 1600px в плитку незачем. */
    public const THUMB = ['w' => 400, 'h' => 400, 'quality' => 80];

    /**
     * Сохранить изображение и вернуть путь на публичном диске.
     *
     * @param  array{w: int, h: int, quality: int}  $size
     */
    public function store(UploadedFile $file, string $directory, array $size): string
    {
        $image = $this->read($file);

        try {
            $resized = $this->fit($image, $size['w'], $size['h']);

            // Имя из случайной строки: оригинальное содержит что угодно,
            // а совпадение имён у разных компаний перезаписало бы файл
            $path = trim($directory, '/').'/'.Str::random(40).'.webp';

            ob_start();
            imagewebp($resized, null, $size['quality']);
            $binary = (string) ob_get_clean();

            if ($resized !== $image) {
                imagedestroy($resized);
            }

            // Сбой записи (переполненный или недоступный диск) — та же
            // понятная ошибка, что и нечитаемый файл, а не страница 500
            try {
                $written = Storage::disk('public')->put($path, $binary);
            } catch (FilesystemException $e) {
                report($e);
                $written = false;
            }

            if ($written === false) {
                throw new RuntimeException('Файл не удалось сохранить');
            }

            return $path;
        } finally {
            imagedestroy($image);
        }
    }

    /** Оригинал и уменьшенная копия одним вызовом. */
    public function storeWithThumb(UploadedFile $file, string $directory): array
    {
        return [
            'path' => $this->store($file, $directory, self::PHOTO),
            'thumb_path' => $this->store($file, $directory.'/thumb', self::THUMB),
        ];
    }

    /** Удалить файл, молча пропустив уже отсутствующий. */
    public function delete(?string ...$paths): void
    {
        foreach (array_filter($paths) as $path) {
            Storage::disk('public')->delete($path);
        }
    }

    /**
     * @return \GdImage
     */
    private function read(UploadedFile $file)
    {
        // Размеры читаются из заголовка (getimagesize не декодирует растр)
        // и проверяются ДО imagecreatefromstring: иначе «бомба распаковки»
        // выделяет гигабайты и роняет процесс фатальной ошибкой памяти,
        // которую вызывающий код перехватить уже не может.
        $info = @getimagesize($file->getRealPath());

        if ($info === false) {
            throw new RuntimeException('Файл не является изображением');
        }

        if (($info[0] * $info[1]) > self::MAX_PIXELS) {
            throw new RuntimeException('Слишком большое изображение');
        }

        $image = @imagecreatefromstring((string) file_get_contents($file->getRealPath()));

        if ($image === false) {
            // Расширение и MIME подделываются заголовком; настоящая
            // проверка — попытка прочитать файл как изображение
            throw new RuntimeException('Файл не является изображением');
        }

        return $image;
    }

    /**
     * Вписать в рамку с сохранением пропорций.
     *
     * Именно вписать, а не обрезать: у товаров бывают вытянутые кадры,
     * и обрезка по центру отрезает как раз то, ради чего фото сняли.
     * Маленькие изображения не растягиваются — увеличение добавляет
     * размер файла и не добавляет деталей.
     *
     * @param  \GdImage  $image
     * @return \GdImage
     */
    private function fit($image, int $maxWidth, int $maxHeight)
    {
        $width = imagesx($image);
        $height = imagesy($image);
        $ratio = min($maxWidth / $width, $maxHeight / $height);

        if ($ratio >= 1) {
            return $image;
        }

        $target = imagecreatetruecolor((int) round($width * $ratio), (int) round($height * $ratio));

        // Прозрачность PNG иначе становится чёрным фоном
        imagealphablending($target, false);
        imagesavealpha($target, true);

        imagecopyresampled(
            $target, $image,
            0, 0, 0, 0,
            imagesx($target), imagesy($target),
            $width, $height,
        );

        return $target;
    }
}
