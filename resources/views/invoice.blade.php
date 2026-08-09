{{--
    Печатная форма счёта.

    Blade, а не страница Inertia: это документ, который несут в банк
    и подшивают в бухгалтерию. Ему нужны свои поля, свой шрифт и
    предсказуемая печать, а не оформление сайта с шапкой и меню.

    PDF не генерируется на сервере намеренно. Браузер печатает
    в PDF сам, одинаково на всех платформах, а серверный генератор —
    это ещё одна зависимость, свои шрифты для кириллицы и свой набор
    отличий от того, что человек видит на экране.
--}}
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <title>Счёт {{ $payment->number }} · SAVDEX</title>
    <style>
        :root { --line: #cbd5e1; --muted: #64748b; }
        * { box-sizing: border-box; }
        body {
            margin: 0; padding: 32px;
            font: 14px/1.5 'Segoe UI', Roboto, Arial, sans-serif;
            color: #0f172a; background: #f1f5f9;
        }
        .sheet {
            max-width: 760px; margin: 0 auto; padding: 40px;
            background: #fff; border-radius: 8px;
        }
        .top { display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; }
        .brand { font-size: 22px; font-weight: 700; letter-spacing: -.02em; }
        .muted { color: var(--muted); }
        h1 { font-size: 20px; margin: 28px 0 4px; }
        table { width: 100%; border-collapse: collapse; margin-top: 24px; }
        th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--line); }
        th { background: #f8fafc; font-size: 13px; text-transform: uppercase; letter-spacing: .04em; }
        td.num, th.num { text-align: right; white-space: nowrap; }
        .total { font-size: 18px; font-weight: 700; }
        dl { display: grid; grid-template-columns: max-content 1fr; gap: 6px 16px; margin: 16px 0 0; }
        dt { color: var(--muted); }
        dd { margin: 0; }
        .note {
            margin-top: 28px; padding: 14px 16px;
            background: #eff6ff; border-radius: 6px; font-size: 13px;
        }
        .sign { margin-top: 48px; display: flex; gap: 48px; }
        .sign div { flex: 1; }
        .sign .line { margin-top: 32px; border-top: 1px solid var(--line); padding-top: 6px; font-size: 12px; color: var(--muted); }
        .actions { max-width: 760px; margin: 0 auto 16px; display: flex; gap: 10px; justify-content: flex-end; }
        .actions button, .actions a {
            padding: 9px 16px; border-radius: 8px; border: 1px solid var(--line);
            background: #fff; color: inherit; text-decoration: none; font: inherit; cursor: pointer;
        }
        .actions button { background: #1d4ed8; color: #fff; border-color: #1d4ed8; }

        /* При печати остаётся только сам документ */
        @media print {
            body { background: #fff; padding: 0; }
            .sheet { max-width: none; padding: 0; border-radius: 0; }
            .actions { display: none; }
        }
    </style>
</head>
<body>
    <div class="actions">
        <a href="/cabinet/billing">Вернуться в кабинет</a>
        <button type="button" onclick="window.print()">Печать или PDF</button>
    </div>

    <div class="sheet">
        <div class="top">
            <div>
                <div class="brand">SAVDEX</div>
                <div class="muted">B2B-площадка Узбекистана и Центральной Азии</div>
            </div>
            <div style="text-align: right">
                <div class="muted">Счёт от {{ $payment->created_at->translatedFormat('d.m.Y') }}</div>
                <div style="font-size: 18px; font-weight: 700">{{ $payment->number }}</div>
                <div class="muted">{{ $payment->statusLabel() }}</div>
            </div>
        </div>

        <h1>Счёт на оплату {{ $payment->number }}</h1>
        <div class="muted">
            {{-- Срок действия называется прямо: просроченный счёт
                 бухгалтерия не проведёт, и знать об этом лучше заранее --}}
            @if ($payment->expiresAt())
                Оплатить до {{ $payment->expiresAt()->translatedFormat('d.m.Y') }}
            @elseif ($payment->paid_at)
                Оплачен {{ $payment->paid_at->translatedFormat('d.m.Y') }}
            @endif
        </div>

        @if ($requisites !== [])
            <dl>
                @foreach ($requisites as $label => $value)
                    <dt>{{ $label }}</dt>
                    <dd>{{ $value }}</dd>
                @endforeach
            </dl>
        @endif

        <dl>
            <dt>Плательщик</dt>
            <dd>{{ $payment->company?->legal_name ?: $payment->company?->name }}</dd>
            @if ($payment->company?->tin)
                <dt>ИНН плательщика</dt>
                <dd>{{ $payment->company->tin }}</dd>
            @endif
        </dl>

        <table>
            <thead>
                <tr>
                    <th style="width: 40px">№</th>
                    <th>Наименование</th>
                    <th class="num">Сумма</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>1</td>
                    <td>{{ $payment->description }}</td>
                    <td class="num">{{ $payment->amountLabel() }}</td>
                </tr>
                <tr>
                    <td></td>
                    <td class="total">Итого к оплате</td>
                    <td class="num total">{{ $payment->amountLabel() }}</td>
                </tr>
            </tbody>
        </table>

        @if ($payment->isPending())
            <div class="note">
                <b>В назначении платежа укажите номер счёта {{ $payment->number }}.</b>
                По нему поступление находят и зачисляют — без него оплата ищется вручную
                и доступ открывается позже.
            </div>
        @endif

        <div class="sign">
            <div>
                <div>Руководитель</div>
                <div class="line">подпись, расшифровка</div>
            </div>
            <div>
                <div>Главный бухгалтер</div>
                <div class="line">подпись, расшифровка</div>
            </div>
        </div>
    </div>
</body>
</html>
