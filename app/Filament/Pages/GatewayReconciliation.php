<?php

declare(strict_types=1);

namespace App\Filament\Pages;

use App\Support\AdminAccess;
use App\Support\Business;
use App\Support\GatewayReconciliation as Recon;
use BackedEnum;
use Filament\Pages\Page;
use Filament\Support\Icons\Heroicon;
use Illuminate\Support\Facades\Cache;
use Livewire\Attributes\Url;
use UnitEnum;

/**
 * Сверка со шлюзом: что площадка начислила против того, что провёл
 * платёжный шлюз (§6.3 ТЗ).
 *
 * Расхождения молчаливы. «Начислили без денег» замечает бухгалтерия
 * в конце квартала, «деньги взяли и не начислили» — клиент, и сразу
 * публично. Экран нужен, чтобы находить их раньше обоих.
 *
 * Значок в меню считает срочные расхождения: если сверку не открывать
 * неделями, она должна сама попроситься.
 */
class GatewayReconciliation extends Page
{
    public static function canAccess(): bool
    {
        return AdminAccess::allows('finreports.view');
    }

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedScale;

    protected static ?string $navigationLabel = 'Сверка со шлюзом';

    protected static string|UnitEnum|null $navigationGroup = 'Монетизация';

    protected static ?int $navigationSort = 9;

    protected string $view = 'filament.pages.gateway-reconciliation';

    #[Url]
    public string $from = '';

    #[Url]
    public string $to = '';

    public function mount(): void
    {
        // Умолчание — местный месяц: по UTC с полуночи до пяти утра
        // первого числа «этот месяц» был бы прошлым
        [$start, $end] = Business::currentMonth();

        $this->from = $this->from !== '' ? $this->from : $start;
        $this->to = $this->to !== '' ? $this->to : $end;
    }

    public function getTitle(): string
    {
        return 'Сверка со шлюзом';
    }

    public function getSubheading(): ?string
    {
        return 'Несогласия между тем, что записала площадка, и тем, что провёл платёжный шлюз.';
    }

    /**
     * Значок в меню — только срочное.
     *
     * Считается за последний месяц, а не за всё время: расхождение
     * трёхлетней давности разбирать поздно, а число, которое никогда
     * не обнуляется, перестают замечать.
     */
    public static function getNavigationBadge(): ?string
    {
        if (! self::canAccess()) {
            return null;
        }

        /*
         * Значок считается на каждой странице админки, а полная сверка
         * поднимает все счета месяца вместе с транзакциями. Замер: три
         * запроса и проход по всем счетам — на каждый показ любой
         * страницы. Пять минут задержки на значке никому не мешают,
         * а нагрузка перестаёт зависеть от того, как часто человек
         * ходит по панели.
         */
        $urgent = Cache::remember('recon.urgent', now()->addMinutes(5), function (): int {
            $summary = Recon::summary(now()->subMonth(), now());

            return $summary[Recon::PERFORMED_WITHOUT_PAID]
                + $summary[Recon::DOUBLE_PERFORMED]
                + $summary[Recon::AMOUNT_MISMATCH];
        });

        return $urgent > 0 ? (string) $urgent : null;
    }

    public static function getNavigationBadgeColor(): ?string
    {
        return 'danger';
    }

    public function setPeriod(string $name): void
    {
        [$from, $to] = match ($name) {
            'prev' => [now()->subMonth()->startOfMonth(), now()->subMonth()->endOfMonth()],
            'quarter' => [now()->startOfQuarter(), now()->endOfQuarter()],
            'year' => [now()->startOfYear(), now()->endOfYear()],
            default => [now()->startOfMonth(), now()->endOfMonth()],
        };

        $this->from = $from->toDateString();
        $this->to = $to->toDateString();
    }

    /** @return array<string, mixed> */
    public function getViewData(): array
    {
        $from = Business::startOfDay($this->from !== '' ? $this->from : Business::currentMonth()[0]);
        $to = Business::endOfDay($this->to !== '' ? $this->to : Business::currentMonth()[1]);

        $findings = Recon::findings($from, $to);

        return [
            'kinds' => Recon::KINDS,
            'grouped' => collect($findings)->groupBy('kind'),
            'total' => count($findings),
        ];
    }
}
