<?php

declare(strict_types=1);

use App\Http\Controllers\Auth\AuthenticatedSessionController;
use App\Http\Controllers\Auth\EmailVerificationController;
use App\Http\Controllers\Auth\ForcePasswordController;
use App\Http\Controllers\Auth\OnboardingController;
use App\Http\Controllers\Auth\PasswordResetController;
use App\Http\Controllers\Auth\RegisteredUserController;
use App\Http\Controllers\Cabinet\AnalyticsController;
use App\Http\Controllers\Cabinet\BillingController;
use App\Http\Controllers\Cabinet\CompanyContactController;
use App\Http\Controllers\Cabinet\CompanyFileController;
use App\Http\Controllers\Cabinet\CompanyProfileController;
use App\Http\Controllers\Cabinet\ContactController;
use App\Http\Controllers\Cabinet\DashboardController;
use App\Http\Controllers\Cabinet\IncomingController;
use App\Http\Controllers\Cabinet\ListingController;
use App\Http\Controllers\Cabinet\ListingImageController;
use App\Http\Controllers\Cabinet\ListingWizardController;
use App\Http\Controllers\Cabinet\PromotionController;
use App\Http\Controllers\Cabinet\ReviewController;
use App\Http\Controllers\Cabinet\SettingsController;
use App\Http\Controllers\LocaleController;
use App\Http\Controllers\NotificationController;
use App\Http\Controllers\Public\CatalogController;
use App\Http\Controllers\Public\CompanyController;
use App\Http\Controllers\Public\ContactUnlockController;
use App\Http\Controllers\Public\FavoriteController;
use App\Http\Controllers\Public\LegalController;
use App\Http\Controllers\Public\NewsController;
use App\Http\Controllers\Public\PageController;
use App\Http\Controllers\Public\SitemapController;
use App\Http\Controllers\Payment\UzumMerchantController;
use App\Http\Controllers\Payment\WebhookController;
use App\Http\Middleware\RequirePasswordChange;
use Illuminate\Support\Facades\Route;

/*
|--------------------------------------------------------------------------
| Публичная часть
|--------------------------------------------------------------------------
*/

Route::get('/', [PageController::class, 'home'])->name('home');
Route::get('/about', [PageController::class, 'about'])->name('about');
Route::get('/pricing', [PageController::class, 'pricing'])->name('pricing');
Route::get('/countries', [PageController::class, 'countries'])->name('countries');
Route::get('/partners', [PageController::class, 'partners'])->name('partners');
Route::get('/contact', [PageController::class, 'contacts'])->name('contacts');

/*
 * Карта сайта. Собирается на лету: объявления появляются и истекают
 * ежедневно, и файл, обновляемый раз в сутки, половину времени
 * присылал бы робота на снятые объявления.
 */
/*
 * robots.txt отдаётся маршрутом, а не файлом в public: адрес карты
 * сайта должен быть абсолютным по спецификации, а домен у площадки
 * разный на каждом окружении.
 */
Route::get('/robots.txt', fn () => response()->view('robots')->header('Content-Type', 'text/plain; charset=utf-8'))
    ->name('robots');

Route::get('/sitemap.xml', [SitemapController::class, 'index'])->name('sitemap');
Route::get('/sitemap-{part}.xml', [SitemapController::class, 'part'])
    ->where('part', '[a-z0-9-]+')
    ->name('sitemap.part');

Route::get('/news', [NewsController::class, 'index'])->name('news');
Route::get('/news/{slug}', [NewsController::class, 'show'])->name('news.show');

/*
 * Колбэк платёжного провайдера.
 *
 * Публичный: провайдер стучится снаружи, без нашей сессии, — поэтому
 * маршрут вне auth и исключён из CSRF (см. bootstrap/app.php). Подлинность
 * проверяется подписью внутри шлюза. Ограничение частоты держит поток
 * повторов в рамках. Выключенный провайдер отдаёт 404.
 */
/*
 * Merchant API Uzum — это не один вебхук «оплачено», а пять вызовов
 * на нашей стороне: check, create, confirm, reverse, status. Все они
 * приходят на подпути одной базы /payments/uzum/callback — именно
 * база сообщается Uzum при подключении. Маршрут стоит раньше общего
 * и потому перехватывает uzum-подпути; защита — Basic auth внутри
 * контроллера, как требует протокол.
 */
Route::post('/payments/uzum/callback/{operation}', [UzumMerchantController::class, 'handle'])
    ->where('operation', '[a-z]+')
    ->middleware('throttle:120,1')
    ->name('payments.uzum.operation');

// Провайдеры с одним вебхуком зовут базу без сегмента операции
Route::post('/payments/{provider}/callback/{operation?}', [WebhookController::class, 'handle'])
    ->where(['provider' => '[a-z]+', 'operation' => '[a-z]+'])
    ->middleware('throttle:120,1')
    ->name('payments.callback');

/*
 * Витрина.
 *
 * Каталог и карточки пишут статистику показов — у них есть цена
 * в запросах к базе, и ограничение частоты держит её в рамках:
 * без него цикл curl роняет базу записями, а не чтениями.
 * 120 в минуту заметно выше живого просмотра и ниже перебора.
 *
 * Скачивание файла тоже здесь: маршрут публичный, но проверка доступа
 * внутри — приватные файлы и непроверенные документы отдаются только
 * своим сотрудникам.
 */
Route::middleware('throttle:120,1')->group(function (): void {
    Route::get('/catalog', [CatalogController::class, 'index'])->name('catalog');
    Route::get('/listing/{slug}', [CatalogController::class, 'show'])->name('listings.show');
    Route::get('/companies', [CompanyController::class, 'index'])->name('companies.index');
    Route::get('/company/{slug}', [CompanyController::class, 'show'])->name('companies.show');
    Route::get('/files/{id}', [CompanyFileController::class, 'download'])->name('files.download');
});

/*
|--------------------------------------------------------------------------
| Вход и регистрация
|--------------------------------------------------------------------------
*/

Route::middleware('guest')->group(function (): void {
    Route::get('/register', [RegisteredUserController::class, 'create'])->name('register');
    /*
     * Ограничение частоты регистраций с одного адреса.
     * Без него фейковые компании заводятся пачками, а на старте
     * маркетплейса доверие к базе — единственный актив.
     */
    Route::post('/register', [RegisteredUserController::class, 'store'])
        ->middleware('throttle:5,60');

    Route::get('/login', [AuthenticatedSessionController::class, 'create'])->name('login');
    Route::post('/login', [AuthenticatedSessionController::class, 'store'])
        ->middleware('throttle:20,1');

    // Восстановление пароля. Маршрут password.reset обязателен:
    // письмо ResetPassword строит ссылку через route('password.reset')
    Route::get('/forgot-password', [PasswordResetController::class, 'request'])->name('password.request');
    Route::post('/forgot-password', [PasswordResetController::class, 'email'])
        ->middleware('throttle:6,1')
        ->name('password.email');
    Route::get('/reset-password/{token}', [PasswordResetController::class, 'reset'])->name('password.reset');
    // Токен угадать нельзя, но подбирать его никто и не мешает
    Route::post('/reset-password', [PasswordResetController::class, 'update'])
        ->middleware('throttle:10,60')
        ->name('password.update');
});

/*
|--------------------------------------------------------------------------
| Личный кабинет
|--------------------------------------------------------------------------
*/

/*
 * RequirePasswordChange закрывает кабинет, пока выданный администратором
 * пароль не заменён своим. Исключения — сама смена, выход, смена языка
 * и подтверждение почты — перечислены в самом посреднике: раньше проверка
 * стояла только на входе, и человек обходил её, набрав /cabinet руками.
 */
Route::middleware(['auth', RequirePasswordChange::class])->group(function (): void {
    Route::post('/logout', [AuthenticatedSessionController::class, 'destroy'])->name('logout');

    /*
     * Подтверждение почты.
     *
     * verification.verify — тот самый маршрут, из-за отсутствия которого
     * регистрация падала с 500: письмо по событию Registered строит ссылку
     * через route('verification.verify'). Ошибка возникала уже после
     * создания пользователя, поэтому аккаунт заводился, а человек видел
     * страницу ошибки и не понимал, зарегистрировался он или нет.
     */
    Route::get('/verify-email', [EmailVerificationController::class, 'notice'])->name('verification.notice');
    Route::get('/verify-email/{id}/{hash}', [EmailVerificationController::class, 'verify'])
        ->middleware(['signed', 'throttle:6,1'])
        ->name('verification.verify');
    Route::post('/email/verification-notification', [EmailVerificationController::class, 'send'])
        ->middleware('throttle:6,1')
        ->name('verification.send');

    Route::get('/password/change', [ForcePasswordController::class, 'edit'])->name('password.forced');
    Route::post('/password/change', [ForcePasswordController::class, 'update'])
        ->middleware('throttle:10,60')
        ->name('password.forced.update');

    /*
     * Второй шаг регистрации. Внутри группы auth, а не guest:
     * пользователь уже создан и вошёл, ему осталось описать компанию.
     */
    Route::get('/onboarding/company', [OnboardingController::class, 'company'])->name('onboarding.company');
    Route::post('/onboarding/company', [OnboardingController::class, 'store'])->name('onboarding.company.store');
    Route::post('/onboarding/skip', [OnboardingController::class, 'skip'])->name('onboarding.skip');

    /*
     * Избранное. Таблица favorites существовала с первого дня
     * (шаг воронки между просмотром и раскрытием контакта), интерфейс
     * появился вместе с новой витриной. Переключение ограничено
     * по частоте: сердечко — запись в базу, а не просмотр.
     */
    Route::get('/favorites', [FavoriteController::class, 'index'])->name('favorites');
    Route::post('/favorites/{id}', [FavoriteController::class, 'toggle'])
        ->whereNumber('id')
        ->middleware('throttle:60,1')
        ->name('favorites.toggle');

    Route::get('/notifications', [NotificationController::class, 'index'])->name('notifications');
    Route::post('/notifications/read-all', [NotificationController::class, 'readAll'])->name('notifications.read-all');
    Route::post('/notifications/{id}/read', [NotificationController::class, 'read'])->name('notifications.read');

    Route::get('/cabinet', DashboardController::class)->name('cabinet');

    Route::get('/cabinet/listings', [ListingController::class, 'index'])->name('cabinet.listings');
    Route::post('/cabinet/listings/bulk', [ListingController::class, 'bulk'])->name('cabinet.listings.bulk');
    Route::post('/cabinet/listings/{id}/renew', [ListingController::class, 'renew'])->name('cabinet.listings.renew');
    Route::post('/cabinet/listings/{id}/archive', [ListingController::class, 'archive'])->name('cabinet.listings.archive');
    Route::post('/cabinet/listings/{id}/resubmit', [ListingController::class, 'resubmit'])->name('cabinet.listings.resubmit');
    Route::delete('/cabinet/listings/{id}', [ListingController::class, 'destroy'])->name('cabinet.listings.destroy');

    /*
     * Публикация требует подтверждённой почты (§5.1 FR-AUTH-02 ТЗ).
     * Скрыть кнопку в интерфейсе недостаточно: адрес открывается напрямую.
     */
    Route::middleware('verified')->group(function (): void {
        Route::get('/cabinet/listings/create', [ListingWizardController::class, 'create'])
            ->middleware('throttle:30,60')
            ->name('cabinet.listings.create');
        Route::get('/cabinet/listings/{id}/edit', [ListingWizardController::class, 'edit'])->name('cabinet.listings.edit');
        // Интерфейс сохраняет раз в 20 секунд — 60 в час с запасом
        Route::post('/cabinet/listings/{id}/autosave', [ListingWizardController::class, 'autosave'])
            ->middleware('throttle:60,1')
            ->name('cabinet.listings.autosave');
        Route::post('/cabinet/listings/{id}/publish', [ListingWizardController::class, 'publish'])->name('cabinet.listings.publish');

        /*
         * Фотографии объявления. Пересборка изображения стоит процессора,
         * поэтому частота ограничена: десять пачек в час хватает
         * на любое разумное заполнение и отсекает перебор.
         */
        Route::post('/cabinet/listings/{id}/images', [ListingImageController::class, 'store'])
            ->middleware('throttle:30,60')
            ->name('cabinet.listings.images.store');
        Route::delete('/cabinet/listings/{id}/images/{imageId}', [ListingImageController::class, 'destroy'])
            ->name('cabinet.listings.images.destroy');
        Route::post('/cabinet/listings/{id}/images/{imageId}/cover', [ListingImageController::class, 'makeCover'])
            ->name('cabinet.listings.images.cover');
    });

    Route::get('/cabinet/contacts', [ContactController::class, 'index'])->name('cabinet.contacts');
    Route::patch('/cabinet/contacts/{id}', [ContactController::class, 'update'])->name('cabinet.contacts.update');
    Route::post('/cabinet/contacts/{id}/complaint', [ContactController::class, 'complain'])->name('cabinet.contacts.complain');
    Route::get('/cabinet/contacts/export', [ContactController::class, 'export'])
        ->middleware('throttle:10,60')
        ->name('cabinet.contacts.export');

    Route::get('/cabinet/incoming', [IncomingController::class, 'index'])->name('cabinet.incoming');
    Route::get('/cabinet/analytics', [AnalyticsController::class, 'index'])->name('cabinet.analytics');

    Route::get('/cabinet/promo', [PromotionController::class, 'index'])->name('cabinet.promo');
    // Тратит единицы продвижения — ограничение обязательно
    Route::post('/cabinet/promo', [PromotionController::class, 'store'])
        ->middleware('throttle:30,60')
        ->name('cabinet.promo.store');

    Route::get('/cabinet/reviews', [ReviewController::class, 'index'])->name('cabinet.reviews');
    Route::post('/cabinet/reviews/{id}/reply', [ReviewController::class, 'reply'])->name('cabinet.reviews.reply');
    Route::post('/cabinet/reviews/{id}/dispute', [ReviewController::class, 'dispute'])->name('cabinet.reviews.dispute');

    /*
     * Отзыв о компании оставляют на её визитке. Право проверяет
     * ReviewService: только тот, кто оплатил раскрытие контактов,
     * и только один раз — иначе рейтинг накручивается за вечер.
     */
    Route::post('/company/{slug}/review', [ReviewController::class, 'store'])
        ->middleware(['verified', 'throttle:20,60'])
        ->name('companies.review');

    /*
     * Раскрытие контактов — ядро монетизации (§3.2 ТЗ).
     * Ограничение частоты обязательно: без него перебором открываются
     * контакты всей базы за минуту, пока хватает кредитов.
     */
    Route::post('/company/{slug}/unlock', [ContactUnlockController::class, 'store'])
        ->middleware(['verified', 'throttle:30,60'])
        ->name('companies.unlock');

    // Контакты компании — тот самый товар, который продаётся
    Route::post('/cabinet/company/contacts', [CompanyContactController::class, 'store'])->name('cabinet.contacts.store');
    Route::patch('/cabinet/company/contacts/{id}', [CompanyContactController::class, 'update'])->name('cabinet.contacts.edit');
    Route::delete('/cabinet/company/contacts/{id}', [CompanyContactController::class, 'destroy'])->name('cabinet.contacts.delete');

    Route::get('/cabinet/company', [CompanyProfileController::class, 'edit'])->name('cabinet.company');
    Route::patch('/cabinet/company', [CompanyProfileController::class, 'update'])->name('cabinet.company.update');

    /*
     * Логотип отдельным запросом: файл нельзя отправить вместе с PATCH,
     * а делать multipart из каждого сохранения профиля незачем.
     */
    Route::post('/cabinet/company/logo', [CompanyProfileController::class, 'uploadLogo'])
        ->middleware('throttle:30,60')
        ->name('cabinet.company.logo');
    Route::delete('/cabinet/company/logo', [CompanyProfileController::class, 'removeLogo'])
        ->name('cabinet.company.logo.remove');

    // 20 МБ на файл: без ограничения частоты диск заполняется за вечер
    Route::post('/cabinet/company/files', [CompanyFileController::class, 'store'])
        ->middleware('throttle:20,60')
        ->name('cabinet.company.files.store');
    Route::patch('/cabinet/company/files/{id}', [CompanyFileController::class, 'update'])->name('cabinet.company.files.update');
    Route::delete('/cabinet/company/files/{id}', [CompanyFileController::class, 'destroy'])->name('cabinet.company.files.destroy');

    Route::get('/cabinet/billing', [BillingController::class, 'index'])->name('cabinet.billing');

    /*
     * Заказ тарифа или пакета кредитов. Требует подтверждённой почты:
     * счёт выставляется на компанию, и её представитель должен быть
     * тем, за кого себя выдаёт.
     */
    Route::post('/cabinet/billing/order', [BillingController::class, 'order'])
        ->middleware(['verified', 'throttle:20,60'])
        ->name('cabinet.billing.order');
    Route::post('/cabinet/billing/invoice/{id}/cancel', [BillingController::class, 'cancelInvoice'])
        ->name('cabinet.billing.invoice.cancel');
    // Онлайн-оплата выставленного счёта: увод на страницу провайдера
    Route::post('/cabinet/billing/invoice/{id}/pay', [BillingController::class, 'pay'])
        ->middleware(['verified', 'throttle:20,60'])
        ->name('cabinet.billing.invoice.pay');
    // Печатная форма: браузер сам сохранит её в PDF
    Route::get('/cabinet/billing/invoice/{id}', [BillingController::class, 'invoice'])
        ->name('cabinet.billing.invoice');
    Route::post('/cabinet/billing/cancel', [BillingController::class, 'cancel'])->name('cabinet.billing.cancel');
    Route::post('/cabinet/billing/resume', [BillingController::class, 'resume'])->name('cabinet.billing.resume');
    Route::delete('/cabinet/billing/card/{id}', [BillingController::class, 'removeCard'])->name('cabinet.billing.card.remove');

    Route::get('/cabinet/settings', [SettingsController::class, 'index'])->name('cabinet.settings');
    Route::patch('/cabinet/settings/notifications', [SettingsController::class, 'notifications'])->name('cabinet.settings.notifications');
    Route::patch('/cabinet/settings/profile', [SettingsController::class, 'profile'])->name('cabinet.settings.profile');
    Route::post('/cabinet/settings/delete', [SettingsController::class, 'destroy'])->name('cabinet.settings.destroy');
});

/*
|--------------------------------------------------------------------------
| Юридические документы
|--------------------------------------------------------------------------
|
| Стоит последним: шаблон {doc} совпадает с любым односегментным адресом.
| Ограничение whereIn не даёт перехватить /login и /catalog, но держать
| такой маршрут в конце — правило, а не необязательная предосторожность.
*/

Route::post('/locale/{locale}', [LocaleController::class, 'update'])->name('locale.update');

Route::get('/{doc}', [LegalController::class, 'show'])
    ->whereIn('doc', ['terms', 'payment', 'security', 'privacy', 'refunds'])
    ->name('legal');
