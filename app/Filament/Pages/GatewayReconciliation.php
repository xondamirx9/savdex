<?php

declare(strict_types=1);

namespace App\Filament\Pages;

use App\Support\AdminAccess;
use App\Support\GatewayReconciliation as Recon;
use BackedEnum;
use Filament\Pages\Page;
use Filament\Support\Icons\Heroicon;
use Illuminate\Support\Carbon;
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
        $this->from = $this->from !== '' ? $this->from : now()->startOfMonth()->toDateString();
        $this->to = $this->to !== '' ? $this->to : now()->endOfMonth()->toDateString();
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

        $summary = Recon::summary(now()->subMonth(), now());
        $urgent = $summary[Recon::PERFORMED_WITHOUT_PAID]
            + $summary[Recon::DOUBLE_PERFORMED]
            + $summary[Recon::AMOUNT_MISMATCH];

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
        $from = Carbon::parse($this->from !== '' ? $this->from : now()->startOfMonth())->startOfDay();
        $to = Carbon::parse($this->to !== '' ? $this->to : now()->endOfMonth())->endOfDay();

        $findings = Recon::findings($from, $to);

        return [
            'kinds' => Recon::KINDS,
            'grouped' => collect($findings)->groupBy('kind'),
            'total' => count($findings),
        ];
    }
}
