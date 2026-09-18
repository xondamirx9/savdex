<?php

declare(strict_types=1);

namespace App\Models;

use App\Services\ReviewService;
use Database\Factories\ReviewFactory;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * Отзыв о компании.
 *
 * Оставить его может только тот, кто оплатил раскрытие контактов —
 * отсюда связь с ContactUnlock. Накрутить рейтинг, не заплатив,
 * невозможно; это обещание вынесено на витрину.
 */
#[Fillable([
    'company_id', 'author_company_id', 'author_user_id', 'contact_unlock_id', 'listing_id',
    'rating', 'rating_description', 'rating_response', 'rating_deadlines', 'rating_quality',
    'body', 'deal_confirmed', 'reply', 'replied_at', 'dispute_status', 'dispute_reason', 'status', 'screening_flags',
    // След решения модератора: кто, когда и с какой формулировкой
    'moderator_note', 'moderated_by', 'moderated_at',
    // Откуда взялся отзыв и кто его завёл, если не покупатель
    'origin', 'created_by',
])]
class Review extends Model
{
    /** @use HasFactory<ReviewFactory> */
    use HasFactory;

    /** Отзыв виден на витрине и участвует в рейтинге. */
    public const STATUS_PUBLISHED = 'published';

    /** Ждёт проверки модератора: в рейтинг и на витрину не попадает. */
    public const STATUS_MODERATION = 'moderation';

    /** Снят по итогам спора или проверки. */
    public const STATUS_HIDDEN = 'hidden';

    /** Написан покупателем в кабинете — обычный путь. */
    public const ORIGIN_BUYER = 'buyer';

    /** Заведён администратором вручную. */
    public const ORIGIN_ADMIN = 'admin';

    /** Загружен пачкой из файла. */
    public const ORIGIN_IMPORT = 'import';

    /**
     * Откуда отзыв, человеческими словами.
     *
     * Показывается только в админке. На сайте отзыв выглядит одинаково
     * независимо от происхождения — так решил владелец площадки; здесь
     * же видно, какая часть рейтинга пришла от покупателей, а какая
     * заведена вручную.
     *
     * @var array<string, string>
     */
    public const ORIGINS = [
        self::ORIGIN_BUYER => 'От покупателя',
        self::ORIGIN_ADMIN => 'Заведён вручную',
        self::ORIGIN_IMPORT => 'Загружен файлом',
    ];

    /** Критерии оценки. Ключ — колонка, значение — подпись в интерфейсе. */
    public const CRITERIA = [
        'rating_description' => 'Соответствие описанию',
        'rating_response' => 'Скорость ответа',
        'rating_deadlines' => 'Соблюдение сроков',
        'rating_quality' => 'Качество товара',
    ];

    /**
     * Умолчания повторяют умолчания столбцов.
     *
     * Без них только что созданный объект отличается от прочитанного
     * из базы: столбец получает значение при вставке, а свойство
     * остаётся пустым — и проверка происхождения отвечает «неизвестно»
     * на обычном покупательском отзыве.
     *
     * @var array<string, mixed>
     */
    protected $attributes = [
        'origin' => self::ORIGIN_BUYER,
    ];

    protected function casts(): array
    {
        return ['deal_confirmed' => 'boolean', 'replied_at' => 'datetime', 'moderated_at' => 'datetime'];
    }

    public function company(): BelongsTo
    {
        return $this->belongsTo(Company::class);
    }

    public function authorCompany(): BelongsTo
    {
        return $this->belongsTo(Company::class, 'author_company_id');
    }

    public function listing(): BelongsTo
    {
        return $this->belongsTo(Listing::class);
    }

    /** Кто принял решение по обращению. */
    /**
     * Рейтинг компании пересчитывается при любом изменении отзыва.
     *
     * Раньше пересчёт звала только модерация: отзывы приходили одним
     * путём — от покупателя, и путь этот всегда шёл через неё. С правкой
     * и загрузкой из админки появились ещё три, и по ним рейтинг не
     * двигался вовсе: администратор заводил отзыв на пять звёзд, а
     * оценка компании на сайте оставалась прежней.
     *
     * Пересчёт идёт только когда изменилось то, что на него влияет.
     * Правка опечатки в тексте рейтинг не трогает.
     */
    protected static function booted(): void
    {
        static::saved(function (self $review): void {
            if (! $review->wasRecentlyCreated
                && ! $review->wasChanged(['rating', 'status', 'company_id'])) {
                return;
            }

            $service = app(ReviewService::class);

            // Отзыв мог переехать к другой компании: пересчитать
            // нужно обе, иначе у прежней останется чужая оценка
            $previous = $review->getOriginal('company_id');

            if ($previous !== null && $previous !== $review->company_id) {
                $before = Company::find($previous);

                if ($before !== null) {
                    $service->recalculate($before);
                }
            }

            $company = Company::find($review->company_id);

            if ($company !== null) {
                $service->recalculate($company);
            }
        });

        static::deleted(function (self $review): void {
            $company = Company::find($review->company_id);

            if ($company !== null) {
                app(ReviewService::class)->recalculate($company);
            }
        });
    }

    /** Администратор, который завёл или загрузил отзыв. */
    public function creator(): BelongsTo
    {
        return $this->belongsTo(User::class, 'created_by');
    }

    public function moderator(): BelongsTo
    {
        return $this->belongsTo(User::class, 'moderated_by');
    }

    public function hasReply(): bool
    {
        return filled($this->reply);
    }
}
