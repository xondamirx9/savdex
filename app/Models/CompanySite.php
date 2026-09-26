<?php

declare(strict_types=1);

namespace App\Models;

use App\Support\Microsite\SiteHost;
use App\Support\Microsite\SiteTheme;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * Мини-сайт компании: адрес на savdex.site и оформление.
 *
 * Содержимого здесь нет — товары, контакты и документы приходят из
 * карточки компании. Компания ведёт всё в одном месте, и объявление,
 * добавленное в кабинете, сразу появляется и на её сайте.
 *
 * Статус и опубликованное оформление меняются только через publish()
 * и unpublish(), поэтому их нет в #[Fillable].
 *
 * @property int $id
 * @property int $company_id
 * @property string $subdomain
 * @property string $status
 * @property array<string, mixed>|null $theme
 * @property array<string, mixed>|null $published_theme
 */
#[Fillable(['company_id', 'subdomain', 'theme'])]
class CompanySite extends Model
{
    public const STATUS_DRAFT = 'draft';

    public const STATUS_PUBLISHED = 'published';

    protected function casts(): array
    {
        return [
            'theme' => 'array',
            'published_theme' => 'array',
            'published_at' => 'datetime',
        ];
    }

    public function company(): BelongsTo
    {
        return $this->belongsTo(Company::class);
    }

    public function url(): string
    {
        return SiteHost::url($this->subdomain);
    }

    /** @return array<string, string> */
    public function draftTheme(): array
    {
        return SiteTheme::normalize($this->theme);
    }

    /** @return array<string, string> */
    public function publishedTheme(): array
    {
        return SiteTheme::normalize($this->published_theme);
    }

    public function isPublished(): bool
    {
        return $this->status === self::STATUS_PUBLISHED;
    }

    /** Черновик отличается от того, что видят посетители. */
    public function hasUnpublishedChanges(): bool
    {
        return ! $this->isPublished() || $this->draftTheme() !== $this->publishedTheme();
    }

    /**
     * Сайт открывается посетителям.
     *
     * Кроме публикации проверяются тариф и блокировка. Тариф — потому
     * что подписка истекает сама, и сайт не должен переживать её:
     * иначе мини-сайт, оплаченный на месяц, работал бы вечно.
     * Блокировка — потому что заблокированная компания исчезает
     * с витрины и не должна оставаться на своём адресе.
     */
    public function isLive(): bool
    {
        return $this->isPublished()
            && ! $this->company->isBlocked()
            && (bool) $this->company->plan()->has_microsite;
    }

    public function publish(): void
    {
        $this->forceFill([
            'status' => self::STATUS_PUBLISHED,
            'published_theme' => $this->draftTheme(),
            'published_at' => now(),
        ])->save();
    }

    public function unpublish(): void
    {
        $this->forceFill(['status' => self::STATUS_DRAFT])->save();
    }
}
