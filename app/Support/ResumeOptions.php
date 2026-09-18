<?php

declare(strict_types=1);

namespace App\Support;

/**
 * Справочники резюме: сферы, занятость, график, уровни языков.
 *
 * Держатся в коде, а не в базе: это не каталог товаров, который
 * растёт от рынка, а короткий список, по которому работает фильтр.
 * Подписи берутся из словаря — раздел говорит на пяти языках, как
 * и всё остальное.
 */
final class ResumeOptions
{
    /**
     * Профессиональные сферы.
     *
     * Составлены под площадку, а не под биржу труда вообще: сюда
     * приходят за снабженцем, логистом и технологом, а не за
     * барменом. «Другое» в конце обязательно — соискателя без
     * подходящего пункта площадка потеряет.
     *
     * @var list<string>
     */
    public const FIELDS = [
        'sales', 'procurement', 'logistics', 'production', 'construction',
        'engineering', 'it', 'finance', 'marketing', 'legal', 'hr',
        'management', 'translation', 'other',
    ];

    /** @var list<string> */
    public const EMPLOYMENT = ['full', 'part', 'project', 'internship'];

    /** @var list<string> */
    public const SCHEDULE = ['full_day', 'shift', 'flexible', 'remote', 'rotational'];

    /** @var list<string> */
    public const LANGUAGE_LEVELS = ['basic', 'intermediate', 'advanced', 'native'];

    /** @var list<string> */
    public const EDUCATION_LEVELS = ['secondary', 'vocational', 'bachelor', 'master', 'phd'];

    /**
     * Ступени опыта для фильтра — как их спрашивают вслух:
     * «без опыта», «от года», «от трёх», «от шести».
     *
     * @var array<string, int> ключ → месяцев не меньше
     */
    public const EXPERIENCE_STEPS = [
        'none' => 0,
        'from1' => 12,
        'from3' => 36,
        'from6' => 72,
    ];

    /**
     * Подписи одного справочника на языке страницы.
     *
     * @param  list<string>  $values
     * @return array<string, string>
     */
    public static function labels(string $group, array $values): array
    {
        $labels = [];

        foreach ($values as $value) {
            $labels[$value] = __("ui.resume.{$group}_{$value}");
        }

        return $labels;
    }

    /** @return array<string, string> */
    public static function fields(): array
    {
        return self::labels('field', self::FIELDS);
    }

    /** @return array<string, string> */
    public static function employment(): array
    {
        return self::labels('employment', self::EMPLOYMENT);
    }

    /** @return array<string, string> */
    public static function schedule(): array
    {
        return self::labels('schedule', self::SCHEDULE);
    }

    /** @return array<string, string> */
    public static function languageLevels(): array
    {
        return self::labels('language_level', self::LANGUAGE_LEVELS);
    }

    /** @return array<string, string> */
    public static function educationLevels(): array
    {
        return self::labels('education_level', self::EDUCATION_LEVELS);
    }

    /** @return array<string, string> */
    public static function experienceSteps(): array
    {
        return self::labels('experience', array_keys(self::EXPERIENCE_STEPS));
    }
}
