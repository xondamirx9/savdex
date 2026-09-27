<?php

declare(strict_types=1);

namespace App\Http\Controllers\Cabinet;

use App\Http\Controllers\Controller;
use App\Models\Company;
use App\Models\CompanySiteProduct;
use App\Support\Currencies;
use App\Support\ImageStore;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Arr;
use Illuminate\Validation\Rule;
use RuntimeException;

/**
 * Товары мини-сайта: заводятся прямо в редакторе сайта.
 *
 * Объявления компании на сайт попадают сами, здесь — то, что компания
 * хочет показать на своей странице без размещения в каталоге площадки.
 * Товары видны на сайте сразу, без публикации: это содержимое, как
 * объявления, а не оформление.
 */
class SiteProductController extends Controller
{
    public function store(Request $request): RedirectResponse
    {
        $company = $this->company($request);

        if ($company === null) {
            return back()->with('error', __('ui.messages.site.plan_required'));
        }

        if ($company->siteProducts()->count() >= CompanySiteProduct::LIMIT) {
            return back()->with('error', __('ui.messages.site.products_limit', ['limit' => CompanySiteProduct::LIMIT]));
        }

        $data = $this->fields($request);

        $product = new CompanySiteProduct([...$data, 'company_id' => $company->id]);

        if (! $this->attachImage($request, $product)) {
            return back()->with('error', __('ui.messages.image.unreadable'));
        }

        $product->save();

        return back()->with('success', __('ui.messages.site.product_saved'));
    }

    public function update(Request $request, int $id): RedirectResponse
    {
        $company = $this->company($request);

        if ($company === null) {
            return back()->with('error', __('ui.messages.site.plan_required'));
        }

        $product = $company->siteProducts()->findOrFail($id);
        $data = $this->fields($request);

        $product->fill($data);

        if (! $this->attachImage($request, $product)) {
            return back()->with('error', __('ui.messages.image.unreadable'));
        }

        $product->save();

        return back()->with('success', __('ui.messages.site.product_saved'));
    }

    /** Удалить можно и без тарифа: это уборка, а не услуга. */
    public function destroy(Request $request, int $id): RedirectResponse
    {
        $product = $request->user()->company?->siteProducts()->findOrFail($id);

        if ($product !== null) {
            app(ImageStore::class)->delete($product->image_path, $product->thumb_path);
            $product->delete();
        }

        return back()->with('success', __('ui.messages.site.product_deleted'));
    }

    private function company(Request $request): ?Company
    {
        $company = $request->user()->company;

        return $company !== null && ! $company->isBlocked() && $company->plan()->has_microsite
            ? $company
            : null;
    }

    /**
     * Проверенные поля товара без файла: фото приходит отдельно
     * через attachImage, в модель его не заливают.
     *
     * @return array<string, mixed>
     */
    private function fields(Request $request): array
    {
        return Arr::except($request->validate($this->rules(), $this->messages()), ['image']);
    }

    /** @return array<string, list<mixed>> */
    private function rules(): array
    {
        return [
            'title' => ['required', 'string', 'min:2', 'max:190'],
            'description' => ['nullable', 'string', 'max:2000'],
            'price' => ['nullable', 'numeric', 'min:0', 'max:99999999999999'],
            'currency' => ['required', Rule::in(Currencies::codes())],
            'unit' => ['nullable', 'string', 'max:30'],
            'image' => ['nullable', 'file', 'mimes:'.implode(',', ImageStore::ALLOWED_MIMES), 'max:'.ImageStore::MAX_SIZE_KB],
        ];
    }

    /** @return array<string, string> */
    private function messages(): array
    {
        return [
            'title.required' => __('ui.messages.site.product_title_required'),
            'image.mimes' => __('ui.messages.image.mimes'),
            'image.max' => __('ui.messages.image.max'),
        ];
    }

    /**
     * Новое фото, если прислали; прежнее удаляется после замены.
     * false — файл не читается как картинка.
     */
    private function attachImage(Request $request, CompanySiteProduct $product): bool
    {
        if (! $request->hasFile('image')) {
            return true;
        }

        $store = app(ImageStore::class);

        try {
            $paths = $store->storeWithThumb($request->file('image'), "sites/{$product->company_id}/products");
        } catch (RuntimeException) {
            return false;
        }

        $store->delete($product->image_path, $product->thumb_path);

        $product->forceFill(['image_path' => $paths['path'], 'thumb_path' => $paths['thumb_path']]);

        return true;
    }
}
