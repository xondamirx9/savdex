<?php

declare(strict_types=1);

namespace Database\Seeders;

use App\Models\ActivityEvent;
use App\Models\Category;
use App\Models\Company;
use App\Models\ContactUnlock;
use App\Models\Listing;
use App\Models\ListingStat;
use App\Models\Payment;
use App\Models\PaymentMethod;
use App\Models\Plan;
use App\Models\Promotion;
use App\Models\PromotionType;
use App\Models\Review;
use App\Models\SearchHit;
use App\Models\Subscription;
use App\Models\User;
use App\Models\UserNotification;
use App\Models\Wallet;
use Illuminate\Database\Seeder;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;

/**
 * Наполнение кабинета демонстрационной компании.
 *
 * Цифры подобраны так, чтобы каждый раздел показывал осмысленную
 * картину: объявления во всех статусах, контакты на разных стадиях
 * воронки, отзыв с ответом и без, продвижение с уже посчитанным
 * эффектом. На пустых таблицах интерфейс нечем проверить.
 */
class CabinetDemoSeeder extends Seeder
{
    public function run(): void
    {
        $company = Company::query()->where('name', 'ООО «Стройбаза»')->first();

        if ($company === null) {
            $this->command?->warn('Нет демо-компании — сначала DemoSeeder.');

            return;
        }

        $user = User::query()->where('email', 'demo@savdex.uz')->first();

        DB::transaction(function () use ($company, $user): void {
            $this->subscribe($company);
            $listings = $this->listings($company, $user);
            $this->stats($listings);
            $this->unlocks($company, $listings);
            $this->requests();
            $this->reviews($company, $listings);
            $this->promotions($company, $listings);
            $this->payments($company);
            $this->events($company);
            $this->notifications($user);
            $this->searchHits($company);
        });

        $this->command?->info('Кабинет наполнен: '.$company->name);
    }

    private function subscribe(Company $company): void
    {
        $plan = Plan::query()->where('code', 'business')->firstOrFail();

        Subscription::updateOrCreate(
            ['company_id' => $company->id, 'status' => 'active'],
            [
                'plan_id' => $plan->id,
                'started_at' => now()->subDays(2),
                'ends_at' => now()->addDays(28),
                'auto_renew' => true,
            ],
        );

        Wallet::updateOrCreate(
            ['company_id' => $company->id],
            [
                'credits' => 12,
                'promo_units' => 38,
                'contacts_used_this_period' => 38,
                'period_resets_at' => now()->addDays(28),
            ],
        );
    }

    /** @return array<string, Listing> */
    private function listings(Company $company, ?User $user): array
    {
        $cement = Category::query()->where('slug', 'cement-beton')->first();
        $pallets = Category::query()->where('slug', 'poddony-tara')->first();
        $metal = Category::query()->where('slug', 'metalloprokat')->first();

        $rows = [
            'cement' => [
                'title' => 'Цемент М400 навалом и в мешках 50 кг, отгрузка с завода',
                'category_id' => $cement?->id,
                'type' => Listing::TYPE_SUPPLY,
                'price' => 1_200_000,
                'unit' => 'т',
                'status' => Listing::STATUS_ACTIVE,
                'published_at' => now()->subDays(62),
                'expires_at' => now()->addDays(92),
                'impressions_count' => 1842,
                'views_count' => 286,
                'unlocks_count' => 14,
                'favorites_count' => 31,
                'description' => 'Портландцемент М400 Д20 с завода в Бекабаде. Отгрузка навалом цементовозами и в мешках по 50 кг. Паспорт качества на каждую партию. Минимальная партия — 20 тонн.',
                'title_i18n' => [
                    'en' => 'Cement M400 in bulk and 50 kg bags, shipped from the plant',
                    'uz' => 'M400 sement — sochma va 50 kg li qoplarda, zavoddan jo‘natiladi',
                    'tr' => 'M400 çimento — dökme ve 50 kg torbalarda, fabrikadan sevkiyat',
                    'zh' => 'M400水泥，散装及50公斤袋装，工厂直发',
                ],
                'description_i18n' => [
                    'en' => 'Portland cement M400 D20 from the plant in Bekabad. Shipped in bulk by cement trucks or in 50 kg bags. Quality certificate for every batch. Minimum order — 20 tonnes.',
                    'uz' => 'Bekoboddagi zavoddan M400 D20 portlandsement. Sement tashuvchi mashinalarda sochma holda yoki 50 kg li qoplarda jo‘natiladi. Har bir partiyaga sifat pasporti beriladi. Eng kam partiya — 20 tonna.',
                    'tr' => 'Bekabad fabrikasından M400 D20 portland çimentosu. Çimento tankerleriyle dökme veya 50 kg torbalarda sevkiyat. Her parti için kalite sertifikası. Minimum sipariş — 20 ton.',
                    'zh' => '别卡巴德工厂生产的M400 D20硅酸盐水泥。可用散装水泥车或50公斤袋装发货。每批附质量证书。最低起订量20吨。',
                ],
            ],
            'gravel' => [
                'title' => 'Щебень фракция 5–20, отгрузка с карьера',
                'category_id' => $cement?->id,
                'type' => Listing::TYPE_SUPPLY,
                'price' => 420_000,
                'unit' => 'м³',
                'status' => Listing::STATUS_ACTIVE,
                // Истекает через три дня — в списке подсвечивается красным
                'published_at' => now()->subDays(87),
                'expires_at' => now()->addDays(3),
                'impressions_count' => 964,
                'views_count' => 118,
                'unlocks_count' => 5,
                'favorites_count' => 12,
                'description' => 'Щебень гранитный фракции 5–20 мм с собственного карьера. Самовывоз или доставка по Ташкентской области.',
                'title_i18n' => [
                    'en' => 'Crushed stone, 5–20 fraction, shipped from the quarry',
                    'uz' => 'Chaqiq tosh, 5–20 fraksiya, karyerdan jo‘natiladi',
                    'tr' => 'Mıcır, 5–20 fraksiyon, ocaktan sevkiyat',
                    'zh' => '碎石，5–20粒级，采石场直发',
                ],
                'description_i18n' => [
                    'en' => 'Granite crushed stone, 5–20 mm fraction, from our own quarry. Pickup or delivery across Tashkent region.',
                    'uz' => 'O‘z karyerimizdan 5–20 mm fraksiyali granit chaqiq tosh. O‘zingiz olib ketishingiz mumkin yoki Toshkent viloyati bo‘ylab yetkazib beramiz.',
                    'tr' => 'Kendi ocağımızdan 5–20 mm fraksiyonlu granit mıcır. Yerinden teslim veya Taşkent bölgesine nakliye.',
                    'zh' => '自有采石场的花岗岩碎石，粒级5–20毫米。可自提或塔什干州范围内配送。',
                ],
            ],
            'pallets' => [
                'title' => 'Куплю поддоны деревянные 1200×800, 2 000 шт',
                'category_id' => $pallets?->id,
                'type' => Listing::TYPE_DEMAND,
                'price' => null,
                'price_negotiable' => true,
                'unit' => 'шт',
                'status' => Listing::STATUS_ACTIVE,
                'published_at' => now()->subDays(14),
                'expires_at' => now()->addDays(48),
                'impressions_count' => 612,
                'views_count' => 94,
                'unlocks_count' => 4,
                'favorites_count' => 7,
                'description' => 'Закупаем поддоны 1200×800 первого и второго сорта. Регулярные объёмы, самовывоз из Ташкента.',
                'title_i18n' => [
                    'en' => 'Buying wooden pallets 1200×800, 2,000 pcs',
                    'uz' => '1200×800 yog‘och pallet sotib olamiz, 2 000 dona',
                    'tr' => '1200×800 ahşap palet alıyoruz, 2.000 adet',
                    'zh' => '求购1200×800木托盘，2000个',
                ],
                'description_i18n' => [
                    'en' => 'We buy 1200×800 pallets, grade 1 and 2. Regular volumes, we arrange pickup from Tashkent.',
                    'uz' => '1200×800 o‘lchamli 1- va 2-nav palletlarni sotib olamiz. Hajmlar muntazam, Toshkentdan o‘zimiz olib ketamiz.',
                    'tr' => '1. ve 2. sınıf 1200×800 palet satın alıyoruz. Düzenli hacimler, Taşkent’ten kendimiz teslim alırız.',
                    'zh' => '收购1200×800一级和二级托盘。需求量稳定，塔什干自提。',
                ],
            ],
            'moderation' => [
                'title' => 'Арматура А500С диаметр 12 мм, прокат в бухтах',
                'category_id' => $metal?->id,
                'type' => Listing::TYPE_SUPPLY,
                'price' => 8_900_000,
                'unit' => 'т',
                'status' => Listing::STATUS_MODERATION,
                'published_at' => null,
                'expires_at' => null,
                'description' => 'Арматура строительная А500С. Резка в размер, доставка манипулятором.',
                'title_i18n' => [
                    'en' => 'Rebar A500C, 12 mm diameter, supplied in coils',
                    'uz' => 'A500C armatura, diametri 12 mm, o‘ramlarda',
                    'tr' => 'A500C inşaat demiri, 12 mm çap, kangal halinde',
                    'zh' => 'A500C螺纹钢，直径12毫米，盘卷供应',
                ],
                'description_i18n' => [
                    'en' => 'Construction rebar A500C. Cut to size, delivered by crane truck.',
                    'uz' => 'A500C qurilish armaturasi. Kerakli o‘lchamda kesib beramiz, manipulyatorli mashinada yetkazamiz.',
                    'tr' => 'A500C inşaat demiri. Ölçüye göre kesim, vinçli araçla teslimat.',
                    'zh' => 'A500C建筑螺纹钢。可按尺寸切割，随车吊送货。',
                ],
            ],
            'draft' => [
                'title' => 'Кирпич керамический полнотелый М150',
                'category_id' => null,
                'type' => Listing::TYPE_SUPPLY,
                'status' => Listing::STATUS_DRAFT,
                'wizard_step' => 2,
                'description' => null,
                'title_i18n' => [
                    'en' => 'Solid ceramic brick M150',
                    'uz' => 'M150 to‘liq tanali keramik g‘isht',
                    'tr' => 'M150 dolu seramik tuğla',
                    'zh' => 'M150实心陶土砖',
                ],
            ],
            'expired' => [
                'title' => 'Песок карьерный мытый, сезонная отгрузка',
                'category_id' => $cement?->id,
                'type' => Listing::TYPE_SUPPLY,
                'price' => 180_000,
                'unit' => 'м³',
                'status' => Listing::STATUS_EXPIRED,
                'published_at' => now()->subDays(160),
                'expires_at' => now()->subDays(12),
                'impressions_count' => 431,
                'views_count' => 52,
                'unlocks_count' => 2,
                'description' => 'Песок мытый для бетонных работ.',
                'title_i18n' => [
                    'en' => 'Washed quarry sand, seasonal shipping',
                    'uz' => 'Yuvilgan karyer qumi, mavsumiy jo‘natish',
                    'tr' => 'Yıkanmış ocak kumu, sezonluk sevkiyat',
                    'zh' => '水洗砂，季节性发货',
                ],
                'description_i18n' => [
                    'en' => 'Washed sand for concrete works.',
                    'uz' => 'Beton ishlari uchun yuvilgan qum.',
                    'tr' => 'Beton işleri için yıkanmış kum.',
                    'zh' => '用于混凝土工程的水洗砂。',
                ],
            ],
            'rejected' => [
                'title' => 'Цемент оптом дёшево',
                'category_id' => $cement?->id,
                'type' => Listing::TYPE_SUPPLY,
                'status' => Listing::STATUS_REJECTED,
                // Причина отказа — из прототипа: телефон в тексте объявления
                'moderation_note' => 'В тексте указан номер телефона. Контакты передаются только через раскрытие контактов площадки.',
                'description' => 'Продаём цемент, звоните по телефону в описании.',
                'title_i18n' => [
                    'en' => 'Cheap wholesale cement',
                    'uz' => 'Ulgurji sement, arzon narxda',
                    'tr' => 'Ucuz toptan çimento',
                    'zh' => '低价批发水泥',
                ],
                'description_i18n' => [
                    'en' => 'We sell cement, call the phone number in the description.',
                    'uz' => 'Sement sotamiz, tavsifda ko‘rsatilgan telefonga qo‘ng‘iroq qiling.',
                    'tr' => 'Çimento satıyoruz, açıklamadaki telefonu arayın.',
                    'zh' => '出售水泥，请拨打描述中的电话。',
                ],
            ],
        ];

        $result = [];

        foreach ($rows as $key => $data) {
            /*
             * Переводы — отдельно от fill(): title_i18n не входит
             * в Fillable, и strict-режим (AppServiceProvider) уронил бы
             * сид. Ставятся до save: с готовым переводом хук saved
             * не отправляет объявление машинному переводчику.
             */
            $i18n = array_intersect_key($data, array_flip(['title_i18n', 'description_i18n']));
            $data = array_diff_key($data, $i18n);

            $listing = Listing::query()->firstOrNew([
                'company_id' => $company->id,
                'title' => $data['title'],
            ]);

            $listing->fill([
                ...$data,
                'company_id' => $company->id,
                'user_id' => $user?->id,
                'city_id' => $company->city_id,
                'currency' => 'UZS',
            ]);

            $listing->forceFill($i18n);
            $listing->save();

            // Адрес строится после сохранения: в него входит id
            if (blank($listing->slug)) {
                $listing->slug = Listing::makeSlug($listing->title, $listing->id);
                $listing->save();
            }

            if (isset($data['moderation_note'])) {
                $listing->moderation_note = $data['moderation_note'];
                $listing->save();
            }

            $result[$key] = $listing;
        }

        return $result;
    }

    /**
     * Статистика за 60 дней с восходящим трендом и недельной волной.
     *
     * Именно 60, а не 30: кабинет сравнивает период с предыдущим таким же.
     * На тридцати днях предыдущий период оказывается пустым, и прирост
     * выходит вида «+1407 %» — цифра, по которой сразу видно, что данные
     * выдуманы. Ровные числа выдают то же самое, поэтому есть тренд
     * и спад на выходных.
     *
     * @param  array<string, Listing>  $listings
     */
    private function stats(array $listings): void
    {
        foreach (['cement' => 1.0, 'gravel' => 0.55, 'pallets' => 0.35] as $key => $weight) {
            $listing = $listings[$key];

            for ($day = 59; $day >= 0; $day--) {
                $date = Carbon::today()->subDays($day);
                $trend = 1 + (59 - $day) * 0.006;
                $weekly = $date->isWeekend() ? 0.6 : 1.0;

                $impressions = (int) round(48 * $weight * $trend * $weekly);
                $views = (int) round($impressions * 0.145);

                ListingStat::updateOrCreate(
                    ['listing_id' => $listing->id, 'date' => $date],
                    [
                        'impressions' => $impressions,
                        'views' => $views,
                        'favorites' => (int) round($views * 0.15),
                        'unlocks' => $day % 4 === 0 ? 1 : 0,
                    ],
                );
            }
        }
    }

    /**
     * Запросы на закупку (RFQ) для ленты «Запросы» на главной.
     *
     * Обратная сторона витрины: не «продаю», а «куплю». Раскладываются
     * по активным компаниям — покупатель у запроса тоже компания.
     * Идемпотентно по паре (компания, заголовок): повторный сид не плодит.
     */
    private function requests(): void
    {
        $companies = Company::query()
            ->where('status', Company::STATUS_ACTIVE)
            ->orderBy('id')
            ->get();

        if ($companies->isEmpty()) {
            return;
        }

        $catId = fn (string $slug): ?int => Category::query()->where('slug', $slug)->value('id');

        // [заголовок, slug категории, единица, описание, переводы заголовка и описания]
        $rows = [
            ['Закупаем цемент М400, 200 т в месяц', 'cement-beton', 'т',
                'Регулярные закупки портландцемента М400 Д20 для монолитного строительства. Нужен стабильный поставщик с паспортом качества и отгрузкой цементовозами.',
                [
                    'en' => 'Buying cement M400, 200 t per month',
                    'uz' => 'M400 sement sotib olamiz, oyiga 200 tonna',
                    'tr' => 'M400 çimento alıyoruz, ayda 200 ton',
                    'zh' => '求购M400水泥，每月200吨',
                ],
                [
                    'en' => 'Regular purchases of Portland cement M400 D20 for monolithic construction. We need a reliable supplier with quality certificates and bulk shipping by cement trucks.',
                    'uz' => 'Monolit qurilish uchun M400 D20 portlandsementni muntazam sotib olamiz. Sifat pasporti bilan, sement tashuvchi mashinalarda jo‘natib beradigan barqaror yetkazib beruvchi kerak.',
                    'tr' => 'Monolitik inşaat için M400 D20 portland çimentosu düzenli alımı. Kalite sertifikalı ve çimento tankeriyle sevkiyat yapabilen istikrarlı bir tedarikçi arıyoruz.',
                    'zh' => '长期采购用于现浇施工的M400 D20硅酸盐水泥。需要有质量证书、能用散装水泥车发货的稳定供应商。',
                ]],
            ['Требуется профлист оцинкованный С8, 5 000 м²', 'metalloprokat', 'м²',
                'Под кровлю склада в Ташкенте. Толщина оцинковки от 0,45 мм, доставка на объект. Готовы к долгосрочному сотрудничеству.',
                [
                    'en' => 'Galvanized profiled sheet C8 needed, 5,000 m²',
                    'uz' => 'S8 rux qoplamali profnastil kerak, 5 000 m²',
                    'tr' => 'C8 galvanizli trapez sac aranıyor, 5.000 m²',
                    'zh' => '需要C8镀锌压型钢板，5000平方米',
                ],
                [
                    'en' => 'For a warehouse roof in Tashkent. Zinc coating from 0.45 mm, delivery to the site. Open to long-term cooperation.',
                    'uz' => 'Toshkentdagi ombor tomi uchun. Rux qoplama qalinligi 0,45 mm dan, obyektga yetkazib berish kerak. Uzoq muddatli hamkorlikka tayyormiz.',
                    'tr' => 'Taşkent’teki depo çatısı için. 0,45 mm’den itibaren galvaniz kaplama, şantiyeye teslimat. Uzun vadeli iş birliğine açığız.',
                    'zh' => '用于塔什干仓库屋面。镀锌层厚度0.45毫米起，送货到工地。愿意长期合作。',
                ]],
            ['Ищем поставщика хлопковой пряжи 30/1', 'tekstil', 'кг',
                'Кардная пряжа для трикотажного производства, объём от 3 тонн в месяц. Приоритет — производителям Ферганской долины.',
                [
                    'en' => 'Looking for a cotton yarn 30/1 supplier',
                    'uz' => '30/1 paxta ipi yetkazib beruvchisini izlaymiz',
                    'tr' => '30/1 pamuk ipliği tedarikçisi arıyoruz',
                    'zh' => '寻找30/1棉纱供应商',
                ],
                [
                    'en' => 'Carded yarn for knitwear production, from 3 tonnes per month. Priority given to Fergana Valley manufacturers.',
                    'uz' => 'Trikotaj ishlab chiqarish uchun karda ip, hajmi oyiga 3 tonnadan. Farg‘ona vodiysi ishlab chiqaruvchilariga ustunlik beriladi.',
                    'tr' => 'Triko üretimi için karde iplik, ayda 3 tondan itibaren. Fergana Vadisi üreticilerine öncelik verilir.',
                    'zh' => '用于针织生产的普梳纱，每月3吨起。费尔干纳河谷的生产商优先。',
                ]],
            ['Нужен щебень фракции 5–20, регулярно', 'cement-beton', 'м³',
                'Для бетонного узла, около 500 м³ в месяц. Самовывоз или доставка по Ташкентской области.',
                [
                    'en' => 'Crushed stone 5–20 needed on a regular basis',
                    'uz' => '5–20 fraksiyali chaqiq tosh kerak, muntazam',
                    'tr' => 'Düzenli olarak 5–20 fraksiyon mıcır gerekli',
                    'zh' => '长期需要5–20粒级碎石',
                ],
                [
                    'en' => 'For a concrete batching plant, about 500 m³ per month. Pickup or delivery across Tashkent region.',
                    'uz' => 'Beton zavodi uchun, oyiga taxminan 500 m³. O‘zimiz olib ketamiz yoki Toshkent viloyati bo‘ylab yetkazib berilsin.',
                    'tr' => 'Beton santrali için, ayda yaklaşık 500 m³. Yerinden alım veya Taşkent bölgesine teslimat.',
                    'zh' => '用于混凝土搅拌站，每月约500立方米。可自提或塔什干州内送货。',
                ]],
            ['Закупка муки пшеничной высшего сорта, 50 т', 'produkty', 'т',
                'Мука в/с для пекарни, регулярные поставки мешками по 50 кг. Нужен сертификат качества.',
                [
                    'en' => 'Purchasing premium-grade wheat flour, 50 t',
                    'uz' => 'Oliy nav bug‘doy uni xarid qilinadi, 50 tonna',
                    'tr' => 'Birinci sınıf buğday unu alımı, 50 ton',
                    'zh' => '采购特级小麦粉，50吨',
                ],
                [
                    'en' => 'Premium-grade flour for a bakery, regular deliveries in 50 kg bags. Quality certificate required.',
                    'uz' => 'Novvoyxona uchun oliy nav un, 50 kg li qoplarda muntazam yetkazib berish. Sifat sertifikati talab qilinadi.',
                    'tr' => 'Fırın için birinci sınıf un, 50 kg torbalarda düzenli teslimat. Kalite sertifikası gerekli.',
                    'zh' => '面包房用特级面粉，50公斤袋装定期供货。需提供质量证书。',
                ]],
        ];

        foreach ($rows as $i => [$title, $slug, $unit, $description, $titleI18n, $descriptionI18n]) {
            $company = $companies[$i % $companies->count()];

            $listing = Listing::query()->firstOrNew([
                'company_id' => $company->id,
                'title' => $title,
            ]);

            $listing->fill([
                'company_id' => $company->id,
                'type' => Listing::TYPE_DEMAND,
                'status' => Listing::STATUS_ACTIVE,
                'category_id' => $catId($slug),
                'price' => null,
                'price_negotiable' => true,
                'unit' => $unit,
                'currency' => 'UZS',
                'city_id' => $company->city_id,
                'published_at' => now()->subDays($i + 1),
                'expires_at' => now()->addDays(50),
                'impressions_count' => 300 + $i * 90,
                'views_count' => 40 + $i * 12,
                'description' => $description,
            ]);

            // Переводы мимо fill и до save — по тем же причинам, что в listings()
            $listing->forceFill(['title_i18n' => $titleI18n, 'description_i18n' => $descriptionI18n]);
            $listing->save();

            if (blank($listing->slug)) {
                $listing->slug = Listing::makeSlug($listing->title, $listing->id);
                $listing->save();
            }
        }
    }

    /** @param array<string, Listing> $listings */
    private function unlocks(Company $company, array $listings): void
    {
        $others = Company::query()->where('id', '!=', $company->id)->get();

        if ($others->isEmpty()) {
            return;
        }

        // По одному объявлению каждой соседней компании: иначе в разделе
        // «Мои контакты» колонка «Объявление» пуста у всех строк,
        // и непонятно, откуда контакт вообще взялся
        $titles = [
            ['Пряжа хлопковая 30/1, кардная', [
                'en' => 'Cotton yarn 30/1, carded',
                'uz' => 'Paxta ipi 30/1, karda',
                'tr' => 'Pamuk ipliği 30/1, karde',
                'zh' => '棉纱30/1，普梳',
            ]],
            ['Бетон товарный М300 с доставкой', [
                'en' => 'Ready-mix concrete M300 with delivery',
                'uz' => 'M300 tayyor beton, yetkazib berish bilan',
                'tr' => 'M300 hazır beton, teslimatlı',
                'zh' => 'M300商品混凝土，含配送',
            ]],
            ['Кирпич керамический М150', [
                'en' => 'Ceramic brick M150',
                'uz' => 'M150 keramik g‘isht',
                'tr' => 'M150 seramik tuğla',
                'zh' => 'M150陶土砖',
            ]],
            ['Профнастил С8 оцинкованный', [
                'en' => 'Galvanized profiled sheet C8',
                'uz' => 'S8 rux qoplamali profnastil',
                'tr' => 'C8 galvanizli trapez sac',
                'zh' => 'C8镀锌压型钢板',
            ]],
            ['Мука пшеничная высшего сорта', [
                'en' => 'Premium-grade wheat flour',
                'uz' => 'Oliy nav bug‘doy uni',
                'tr' => 'Birinci sınıf buğday unu',
                'zh' => '特级小麦粉',
            ]],
        ];

        foreach ($others as $i => $other) {
            [$title, $titleI18n] = $titles[$i % count($titles)];

            // Ранее посеянное объявление находится по заголовку: повторный
            // сид дописывает переводы, а не пропускает компанию
            $listing = $other->listings()->where('title', $title)->first();

            if ($listing === null) {
                if ($other->listings()->exists()) {
                    continue;
                }

                $listing = $other->listings()->make([
                    'title' => $title,
                    'type' => Listing::TYPE_SUPPLY,
                    'status' => Listing::STATUS_ACTIVE,
                    'currency' => 'UZS',
                    'city_id' => $other->city_id,
                    'published_at' => now()->subDays(30),
                    'expires_at' => now()->addDays(60),
                ]);
            }

            // Перевод до save: хук saved не должен слать объявление в переводчик
            $listing->forceFill(['title_i18n' => $titleI18n]);
            $listing->save();

            if (blank($listing->slug)) {
                $listing->slug = Listing::makeSlug($listing->title, $listing->id);
                $listing->save();
            }
        }

        // Контакты, которые открыли мы — на разных стадиях воронки
        $mine = [
            ['status' => 'deal', 'note' => 'Отгрузили 5 т, качество ок', 'days' => 4],
            ['status' => 'negotiating', 'note' => 'Ждём КП до пятницы', 'days' => 7],
            ['status' => 'rejected', 'note' => 'Не возят в Ташкент', 'days' => 10],
            ['status' => 'contacted', 'note' => 'Перезвонить после 15-го', 'days' => 15],
            ['status' => 'new', 'note' => null, 'days' => 1],
        ];

        foreach ($others->take(count($mine)) as $i => $target) {
            ContactUnlock::updateOrCreate(
                ['company_id' => $company->id, 'target_company_id' => $target->id],
                [
                    'listing_id' => $target->listings()->value('id'),
                    'credits_spent' => 1,
                    'status' => $mine[$i]['status'],
                    'note' => $mine[$i]['note'],
                    'created_at' => now()->subDays($mine[$i]['days']),
                ],
            );
        }

        // Кто открыл наши контакты — раздел «Кто мной интересуется»
        $incoming = [
            ['listing' => 'cement', 'minutes' => 18],
            ['listing' => 'gravel', 'minutes' => 1500],
            ['listing' => 'cement', 'minutes' => 3200],
        ];

        foreach ($others->take(count($incoming)) as $i => $source) {
            ContactUnlock::updateOrCreate(
                ['company_id' => $source->id, 'target_company_id' => $company->id],
                [
                    'listing_id' => $listings[$incoming[$i]['listing']]->id,
                    'credits_spent' => 1,
                    'status' => 'new',
                    'created_at' => now()->subMinutes($incoming[$i]['minutes']),
                ],
            );
        }
    }

    /** @param array<string, Listing> $listings */
    private function reviews(Company $company, array $listings): void
    {
        $authors = Company::query()->where('id', '!=', $company->id)->get();

        if ($authors->count() < 2) {
            return;
        }

        Review::updateOrCreate(
            [
                'company_id' => $company->id,
                'author_company_id' => $authors[0]->id,
                'listing_id' => $listings['cement']->id,
            ],
            [
                'rating' => 5,
                'rating_description' => 5,
                'rating_response' => 5,
                'rating_deadlines' => 5,
                'rating_quality' => 5,
                'body' => 'Заказывали 60 тонн М400. Отгрузили день в день, паспорт качества приложили без напоминаний. Работаем дальше.',
                'deal_confirmed' => true,
                'status' => 'published',
                'created_at' => now()->subHours(3),
            ],
        );

        Review::updateOrCreate(
            [
                'company_id' => $company->id,
                'author_company_id' => $authors[1]->id,
                'listing_id' => $listings['gravel']->id,
            ],
            [
                'rating' => 3,
                'rating_description' => 4,
                'rating_response' => 3,
                'rating_deadlines' => 2,
                'rating_quality' => 4,
                'body' => 'Товар нормальный, но доставку задержали на два дня и предупредили постфактум.',
                'deal_confirmed' => false,
                'reply' => 'Приносим извинения, задержка из-за ремонта на карьере. Компенсировали скидкой на следующую партию.',
                'replied_at' => now()->subDays(15),
                'status' => 'published',
                'created_at' => now()->subDays(16),
            ],
        );

        $this->recalculateRating($company);
    }

    private function recalculateRating(Company $company): void
    {
        $reviews = $company->reviews()->get();

        $company->forceFill([
            'rating' => round((float) $reviews->avg('rating'), 1),
            'reviews_count' => $reviews->count(),
        ])->save();
    }

    /** @param array<string, Listing> $listings */
    private function promotions(Company $company, array $listings): void
    {
        $top = PromotionType::query()->where('code', 'category_top')->first();
        $urgent = PromotionType::query()->where('code', 'urgent')->first();

        if ($top !== null) {
            Promotion::updateOrCreate(
                ['listing_id' => $listings['cement']->id, 'promotion_type_id' => $top->id],
                [
                    'company_id' => $company->id,
                    'category_id' => $listings['cement']->category_id,
                    'units_spent' => $top->cost_units,
                    'status' => 'active',
                    'starts_at' => now()->subDays(5),
                    'ends_at' => now()->addDays(2),
                    'impressions_before' => 412,
                    'impressions_after' => 1430,
                ],
            );
        }

        if ($urgent !== null) {
            Promotion::updateOrCreate(
                ['listing_id' => $listings['gravel']->id, 'promotion_type_id' => $urgent->id],
                [
                    'company_id' => $company->id,
                    'category_id' => $listings['gravel']->category_id,
                    'units_spent' => $urgent->cost_units,
                    'status' => 'active',
                    'starts_at' => now()->subDays(3),
                    'ends_at' => now()->addDays(4),
                    'impressions_before' => 318,
                    'impressions_after' => 604,
                ],
            );
        }
    }

    private function payments(Company $company): void
    {
        $card = PaymentMethod::updateOrCreate(
            ['company_id' => $company->id, 'last4' => '4417'],
            [
                'provider' => 'payme',
                'token' => 'demo-token-not-a-card-number',
                'brand' => 'Uzcard',
                'expires' => '09/28',
                'is_default' => true,
            ],
        );

        $history = [
            ['Тариф Business, 1 мес.', 489_000, 'subscription', 2, 'payme'],
            ['Пакет 20 кредитов', 370_000, 'credits', 14, 'click'],
            ['Тариф Business, 1 мес.', 489_000, 'subscription', 32, 'payme'],
            ['Пакет 50 единиц продвижения', 250_000, 'promo_units', 40, 'payme'],
        ];

        foreach ($history as [$description, $amount, $purpose, $daysAgo, $provider]) {
            Payment::updateOrCreate(
                ['company_id' => $company->id, 'description' => $description, 'paid_at' => now()->subDays($daysAgo)->startOfMinute()],
                [
                    'payment_method_id' => $provider === 'payme' ? $card->id : null,
                    'purpose' => $purpose,
                    'amount' => $amount,
                    'currency' => 'UZS',
                    'provider' => $provider,
                    'status' => 'paid',
                ],
            );
        }
    }

    /**
     * Персональные уведомления демо-пользователю.
     *
     * Дублируют часть событий ленты: событие принадлежит компании,
     * уведомление — человеку и имеет состояние прочтения.
     */
    private function notifications(?User $user): void
    {
        if ($user === null) {
            return;
        }

        $rows = [
            ['contact_unlocked', 'success', 'Компания из Самарканда открыла ваш контакт', 'Объявление «Цемент М400 навалом». Это тёплый лид — с вами уже готовы говорить.', '/cabinet/incoming', 18, false],
            ['new_review', 'warning', 'Новый отзыв: 5 звёзд от «Andijon Tekstil»', 'Отгрузили день в день, паспорт качества приложили без напоминаний.', '/cabinet/reviews', 180, false],
            ['listing_expiring', 'danger', 'Объявление «Щебень фр. 5–20» истекает через 3 дня', 'После истечения показы прекращаются. Продлите в один клик.', '/cabinet/listings', 1440, true],
            ['moderation', 'info', 'Объявление «Арматура А500С» отправлено на модерацию', 'Обычно проверка занимает до 2 часов в рабочее время.', '/cabinet/listings?status=moderation', 2880, true],
            ['broadcast', 'info', 'Оплата через Click и Uzum', 'К Payme добавились ещё два способа оплаты в сумах. Автопродление работает по сохранённой карте.', '/news/oplata-click-uzum', 4320, true],
        ];

        foreach ($rows as [$type, $tone, $title, $body, $url, $minutesAgo, $read]) {
            UserNotification::updateOrCreate(
                ['user_id' => $user->id, 'title' => $title],
                [
                    'company_id' => $user->company_id,
                    'type' => $type,
                    'tone' => $tone,
                    'body' => $body,
                    'url' => $url,
                    'is_broadcast' => $type === 'broadcast',
                    'read_at' => $read ? now()->subMinutes($minutesAgo - 10) : null,
                    'created_at' => now()->subMinutes($minutesAgo),
                ],
            );
        }
    }

    private function events(Company $company): void
    {
        $events = [
            ['unlock', 'success', 'Компания из Самарканда открыла ваш контакт по объявлению «Цемент М400»', 18],
            ['review', 'warning', 'Новый отзыв: 5 звёзд от «ТехноСтрой» — «отгрузили в срок»', 180],
            ['promotion', 'info', 'Продвижение «ТОП категории» на объявлении «Цемент М400» истекает через 2 дня', 600],
            ['expiry', 'danger', 'Объявление «Щебень фр. 5–20» истекает через 3 дня — продлите', 1440],
            ['moderation', 'info', 'Объявление «Арматура А500С» отправлено на модерацию', 2880],
        ];

        foreach ($events as [$type, $tone, $message, $minutesAgo]) {
            ActivityEvent::updateOrCreate(
                ['company_id' => $company->id, 'message' => $message],
                [
                    'type' => $type,
                    'tone' => $tone,
                    'created_at' => now()->subMinutes($minutesAgo),
                ],
            );
        }
    }

    private function searchHits(Company $company): void
    {
        $queries = [
            ['цемент м400 ташкент', 842, 164],
            ['цемент оптом', 618, 88],
            ['портландцемент д20', 294, 61],
            ['щебень 5 20 цена', 271, 34],
            ['поддоны бу купить', 148, 22],
        ];

        foreach ($queries as [$query, $impressions, $clicks]) {
            SearchHit::updateOrCreate(
                ['company_id' => $company->id, 'query' => $query, 'date' => Carbon::today()],
                ['impressions' => $impressions, 'clicks' => $clicks],
            );
        }
    }
}
