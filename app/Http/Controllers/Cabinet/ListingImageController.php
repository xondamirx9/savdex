<?php

declare(strict_types=1);

namespace App\Http\Controllers\Cabinet;

use App\Http\Controllers\Controller;
use App\Models\Listing;
use App\Support\ImageStore;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use RuntimeException;

/**
 * Фотографии объявления.
 *
 * Мастер обещает, что объявления с фото открывают заметно чаще, —
 * и до сих пор предлагал вместо загрузки надпись «появится позже».
 *
 * Первая по порядку фотография служит обложкой: отдельного флага нет,
 * потому что «сделать обложкой» и «поставить первой» — одно и то же
 * действие, и два способа сказать одно приводят к рассинхрону.
 */
class ListingImageController extends Controller
{
    /** Больше десяти фотографий никто не листает, а место они занимают. */
    private const MAX_IMAGES = 10;

    public function store(Request $request, int $id): RedirectResponse
    {
        $listing = $this->owned($request, $id);

        $request->validate([
            'images' => ['required', 'array', 'max:'.self::MAX_IMAGES],
            'images.*' => [
                'file',
                'mimes:'.implode(',', ImageStore::ALLOWED_MIMES),
                'max:'.ImageStore::MAX_SIZE_KB,
            ],
        ], [
            'images.required' => 'Выберите фотографии',
            'images.*.mimes' => 'Допустимы JPG, PNG и WebP',
            'images.*.max' => 'Файл больше 8 МБ. Уменьшите разрешение или сожмите',
        ]);

        $already = $listing->images()->count();
        $files = $request->file('images');
        $free = self::MAX_IMAGES - $already;

        if ($free <= 0) {
            return back()->with('error', 'Больше '.self::MAX_IMAGES.' фотографий к одному объявлению не прикрепить');
        }

        // Лишние отсекаем, но загружаем то, что помещается: отказывать
        // во всей пачке из-за одной лишней — повод загружать заново
        $files = array_slice($files, 0, $free);
        $store = app(ImageStore::class);
        $saved = 0;

        foreach ($files as $file) {
            try {
                $paths = $store->storeWithThumb($file, "listings/{$listing->id}");
            } catch (RuntimeException) {
                // Один битый файл не должен рушить загрузку остальных
                continue;
            }

            $listing->images()->create([
                ...$paths,
                'sort' => $already + $saved,
            ]);

            $saved++;
        }

        if ($saved === 0) {
            return back()->with('error', 'Ни один файл не удалось прочитать как изображение');
        }

        $skipped = count($request->file('images')) - $saved;

        return back()->with('success', $skipped > 0
            ? "Загружено фотографий: {$saved}. Пропущено: {$skipped}."
            : "Загружено фотографий: {$saved}");
    }

    public function destroy(Request $request, int $id, int $imageId): RedirectResponse
    {
        $listing = $this->owned($request, $id);
        $image = $listing->images()->find($imageId);

        abort_if($image === null, 404);

        app(ImageStore::class)->delete($image->path, $image->thumb_path);
        $image->delete();

        $this->resequence($listing);

        return back()->with('success', 'Фотография удалена');
    }

    /** Сделать обложкой — то есть поставить первой. */
    public function makeCover(Request $request, int $id, int $imageId): RedirectResponse
    {
        $listing = $this->owned($request, $id);
        $image = $listing->images()->find($imageId);

        abort_if($image === null, 404);

        $image->forceFill(['sort' => -1])->save();

        $this->resequence($listing);

        return back()->with('success', 'Фотография стала обложкой');
    }

    /**
     * Пронумеровать заново от нуля.
     *
     * После удаления и перестановок в sort остаются дыры и временное
     * -1; порядок от этого не ломается, но следующая вставка «в конец»
     * считается по количеству и попадает в середину.
     */
    private function resequence(Listing $listing): void
    {
        foreach ($listing->images()->orderBy('sort')->get()->values() as $index => $image) {
            if ($image->sort !== $index) {
                $image->forceFill(['sort' => $index])->save();
            }
        }
    }

    private function owned(Request $request, int $id): Listing
    {
        $company = $request->user()->company;

        abort_if($company === null, 404);

        $listing = $company->listings()->find($id);

        abort_if($listing === null, 404);

        return $listing;
    }
}
