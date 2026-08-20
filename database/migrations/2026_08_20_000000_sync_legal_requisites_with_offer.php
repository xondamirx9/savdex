<?php

declare(strict_types=1);

use App\Models\Setting;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Реквизиты оператора по утверждённой публичной оферте.
 *
 * Оферта — документ, поданный в банк-эквайер, и реквизиты на витрине
 * обязаны совпадать с ней до знака: расхождение ИНН на странице
 * «О компании» и в оферте банк читает как признак подставной площадки.
 * Поэтому значения проставляются по документу, а не «если пусто»:
 * до этой миграции в базе стояли заглушки сидера (ИНН 000000000),
 * и страница показывала их как настоящий ИНН.
 *
 * Дальше реквизиты правятся в админке — миграция выполняется однократно
 * и введённое после неё не трогает.
 *
 * Новые ключи (адреса, руководитель, банк) заводятся здесь же: сидер
 * наполняет только свежую базу, на работающем стенде строки пришлось бы
 * заводить руками.
 */
return new class extends Migration
{
    /**
     * Реквизиты из раздела 22 оферты.
     *
     * @var array<string, array{label: string, value: string, description: string|null, sort: int}>
     */
    private const REQUISITES = [
        'legal_full_name' => [
            'label' => 'Полное наименование',
            'value' => '"ANJIR-GROUP" MAS\'ULIYATI CHEKLANGAN JAMIYAT',
            'description' => 'Точное наименование юридического лица как в учредительных документах. Показывается в разделе «Реквизиты» публичной оферты и в счёте',
            'sort' => 20,
        ],
        'legal_brand' => [
            'label' => 'Торговое наименование',
            'value' => 'SavdEx',
            'description' => null,
            'sort' => 21,
        ],
        'legal_tin' => [
            'label' => 'ИНН',
            'value' => '312525684',
            'description' => 'Должен совпадать с ИНН в публичной оферте — расхождение блокирует проверку банка-эквайера',
            'sort' => 22,
        ],
        'legal_address' => [
            'label' => 'Юридический адрес',
            'value' => 'Toshkent shahri, Shayxontohur tumani, Hadra MFY, Hadra mavzesi, 5-uy, 54-xonadon',
            'description' => null,
            'sort' => 23,
        ],
        'legal_actual_address' => [
            'label' => 'Фактический адрес',
            'value' => 'Toshkent shahri, Shayxontohur tumani, Furkat 1/1',
            'description' => null,
            'sort' => 24,
        ],
        'legal_phone' => [
            'label' => 'Телефон юридического лица',
            'value' => '+998 90 031-30-77',
            'description' => 'Телефон из реквизитов оферты. Телефон поддержки для посетителей задаётся отдельно, в группе «Контакты»',
            'sort' => 25,
        ],
        'legal_email' => [
            'label' => 'E-mail юридического лица',
            'value' => 'Infoanjirgroup@gmail.com',
            'description' => 'Почта из реквизитов оферты. Почта поддержки задаётся отдельно, в группе «Контакты»',
            'sort' => 26,
        ],
        'legal_bank' => [
            'label' => 'Банк',
            'value' => '"IPAK YO\'LI" AIT Banking Bosh O\'fisi',
            'description' => null,
            'sort' => 27,
        ],
        'legal_mfo' => [
            'label' => 'Код банка (МФО)',
            'value' => '00444',
            'description' => null,
            'sort' => 28,
        ],
        'legal_account' => [
            'label' => 'Расчётный счёт',
            'value' => '20208000507335080001',
            'description' => null,
            'sort' => 29,
        ],
        'legal_director' => [
            'label' => 'Руководитель',
            'value' => 'ABDUHAMIDOV ABDURASHID ABDUVOHID OGLI',
            'description' => null,
            'sort' => 30,
        ],
    ];

    /** Пример из подсказки к настройке — не адрес офиса, а картинка «как заполнять». */
    private const COORDS_EXAMPLE = '41.311081, 69.240562';

    public function up(): void
    {
        $now = now();

        foreach (self::REQUISITES as $key => $row) {
            $exists = DB::table('settings')->where('key', $key)->exists();

            if ($exists) {
                /*
                 * sort обновляется вместе со значением: у ключей,
                 * заведённых сидером, он свой, и без выравнивания
                 * реквизиты в админке встали бы вперемешку — новые
                 * строки перед наименованием, счёт до банка.
                 */
                DB::table('settings')->where('key', $key)->update([
                    'label' => $row['label'],
                    'description' => $row['description'],
                    'value' => json_encode($row['value']),
                    'sort' => $row['sort'],
                    'updated_at' => $now,
                ]);

                continue;
            }

            DB::table('settings')->insert([
                'group' => 'legal',
                'key' => $key,
                'label' => $row['label'],
                'description' => $row['description'],
                'type' => 'string',
                'value' => json_encode($row['value']),
                'sort' => $row['sort'],
                'created_at' => $now,
                'updated_at' => $now,
            ]);
        }

        // Краткое наименование остаётся первым в группе: значение
        // менять незачем, но порядок должен быть рядом с полным
        DB::table('settings')->where('key', 'legal_name')->update(['sort' => 19, 'updated_at' => $now]);

        $this->syncOfficeAddress($now);
        $this->fixPaymentNews($now);

        // Настройки читаются из суточного кэша: без сброса реквизиты
        // в оферте обновились бы не сразу после деплоя
        Setting::flushCache();
    }

    /**
     * Адрес офиса на витрине — фактический адрес из оферты.
     *
     * Страница «О компании» показывает адрес офиса, оферта — фактический
     * адрес юрлица. До этой миграции там стояли разные районы города:
     * посетитель и банк-эквайер видели два адреса одной компании.
     *
     * Координаты при этом гасятся, а не переносятся: прежние указывали
     * на центр Ташкента — пример из подсказки к настройке, а не на офис.
     * Без координат раздел показывает адрес без карты; настоящую точку
     * администратор поставит в админке.
     */
    private function syncOfficeAddress(mixed $now): void
    {
        $actual = self::REQUISITES['legal_actual_address']['value'];

        DB::table('settings')
            ->where('key', 'office_address')
            ->update(['value' => json_encode($actual), 'updated_at' => $now]);

        /*
         * Сравнение идёт в PHP, а не условием в запросе: колонка value
         * объявлена как json, и Postgres не умеет сравнивать её со
         * строкой — «operator does not exist: json = text». SQLite такое
         * сравнение проглатывает, поэтому на локальной базе промах
         * не виден, а деплой падает на первой же миграции.
         */
        $coords = DB::table('settings')->where('key', 'office_coords')->value('value');

        if ($coords !== null && json_decode((string) $coords, true) === self::COORDS_EXAMPLE) {
            DB::table('settings')
                ->where('key', 'office_coords')
                ->update(['value' => json_encode(''), 'updated_at' => $now]);
        }
    }

    /**
     * Новость о способах оплаты — по фактически подключённому эквайрингу.
     *
     * Сидер опубликовал новость, обещавшую Payme, Click и списание
     * за продление по сохранённому токену. Ничего из этого на площадке
     * нет: платежи идут через интернет-эквайринг Uzum Bank, а продление
     * выставляет счёт. Новость лежит на витрине рядом со страницей
     * «Способы оплаты» и противоречит ей — а её читает и банк-эквайер.
     *
     * Правится только неотредактированный сидерский текст: новость,
     * переписанную в админке, миграция не трогает.
     */
    private function fixPaymentNews(mixed $now): void
    {
        $post = DB::table('news_posts')->where('slug', 'oplata-click-uzum')->first();

        if ($post === null || ! str_contains((string) $post->body, 'Payme')) {
            return;
        }

        DB::table('news_posts')->where('id', $post->id)->update([
            'title' => 'Оплата картами через интернет-эквайринг Uzum Bank',
            'excerpt' => 'Uzcard, Humo, Visa и Mastercard — в сумах, с подтверждением 3-D Secure.',
            'body' => "Оплатить подписку и пакеты кредитов можно банковскими картами Uzcard, Humo, Visa и Mastercard через сервис интернет-эквайринга АО «Uzum Bank», в сумах.\n\nРеквизиты карты вводятся на защищённой платёжной странице банка: площадка не получает и не хранит номер карты и код CVV. Каждый платёж подтверждается одноразовым кодом 3-D Secure, который присылает банк, выпустивший карту.\n\nПри включённом автопродлении счёт на следующий период выставляется за неделю до окончания оплаченного — деньги с карты при этом не списываются. Отключить автопродление можно в кабинете, в разделе «Тариф и оплата».\n\nПодробнее — на страницах «Способы оплаты» и «Безопасность платежей».",
            'updated_at' => $now,
        ]);
    }

    public function down(): void
    {
        /*
         * Откатываются только строки, которых до миграции не было.
         * Прежние значения ИНН и банковских реквизитов были заглушками
         * сидера, и возвращать их незачем — восстановленный «ИНН
         * 000000000» на витрине хуже отсутствия отката.
         */
        DB::table('settings')->whereIn('key', [
            'legal_full_name', 'legal_brand', 'legal_address',
            'legal_actual_address', 'legal_phone', 'legal_email', 'legal_director',
        ])->delete();

        Setting::flushCache();
    }
};
