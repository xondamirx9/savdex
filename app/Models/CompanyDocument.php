<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * Файл компании: документ для проверки либо материал для визитки.
 *
 * Две разные роли в одной таблице — намеренно. Различает их не тип
 * хранилища, а назначение: документы уходят модератору и влияют на
 * уровень верификации, материалы сразу показываются партнёрам.
 * Разводить их по двум таблицам значило бы дублировать загрузку,
 * валидацию и удаление файлов.
 */
class CompanyDocument extends Model
{
    public const STATUS_PENDING = 'pending';

    public const STATUS_APPROVED = 'approved';

    public const STATUS_REJECTED = 'rejected';

    /**
     * Документы для верификации. Проходят модерацию, на визитке
     * показываются только после одобрения.
     */
    public const VERIFICATION_TYPES = [
        'registration' => 'Свидетельство о регистрации',
        'license' => 'Лицензия',
        'certificate' => 'Сертификат',
        'quality' => 'Паспорт качества',
    ];

    /**
     * Материалы для партнёров. Модерация им не нужна: это не
     * подтверждение статуса, а рекламные материалы самой компании.
     */
    public const MATERIAL_TYPES = [
        'presentation' => 'Презентация',
        'price_list' => 'Прайс-лист',
        'catalog' => 'Каталог продукции',
        'other' => 'Другой файл',
    ];

    /** Что разрешено загружать. Исполняемые файлы недопустимы. */
    public const ALLOWED_MIMES = [
        'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'jpg', 'jpeg', 'png', 'zip',
    ];

    public const MAX_SIZE_KB = 20480;

    public function typeLabel(): string
    {
        return self::VERIFICATION_TYPES[$this->type]
            ?? self::MATERIAL_TYPES[$this->type]
            ?? $this->type;
    }

    /** Материал для партнёров, а не документ для модератора. */
    public function isMaterial(): bool
    {
        return array_key_exists($this->type, self::MATERIAL_TYPES);
    }

    /**
     * Виден ли файл на визитке.
     *
     * Материалы — сразу, документы — только после одобрения: показывать
     * непроверенную лицензию значит давать компании подтверждение,
     * которого она не получала.
     */
    public function isVisibleOnCard(): bool
    {
        if (! $this->is_public) {
            return false;
        }

        return $this->isMaterial() || $this->moderation_status === self::STATUS_APPROVED;
    }

    /** Размер для человека: «2,4 МБ» вместо 2516582. */
    public function sizeLabel(): ?string
    {
        if ($this->file_size === null) {
            return null;
        }

        return $this->file_size >= 1048576
            ? number_format($this->file_size / 1048576, 1, ',', ' ').' МБ'
            : number_format($this->file_size / 1024, 0, ',', ' ').' КБ';
    }

    protected $fillable = [
        'company_id', 'type', 'title', 'file_path', 'file_size', 'mime',
        'valid_until', 'is_public', 'moderation_status', 'moderation_note',
        // След решения модератора: кто и когда проверил документ
        'moderated_by', 'moderated_at',
    ];

    protected function casts(): array
    {
        return [
            'valid_until' => 'date',
            'is_public' => 'boolean',
            'file_size' => 'integer',
            'moderated_at' => 'datetime',
        ];
    }

    public function company(): BelongsTo
    {
        return $this->belongsTo(Company::class);
    }

    /** Кто проверил документ. */
    public function moderator(): BelongsTo
    {
        return $this->belongsTo(User::class, 'moderated_by');
    }

    /** Просроченный сертификат не должен считаться подтверждением надёжности. */
    public function isExpired(): bool
    {
        return $this->valid_until !== null && $this->valid_until->isPast();
    }
}
