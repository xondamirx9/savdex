import { Check } from 'lucide-react';
import { cn } from '@/lib/cn';
import { t } from '@/lib/i18n';

/**
 * Полоска «Почта → Код → Данные» над формами регистрации.
 * Пройденные шаги отмечены галочкой, текущий — номером на синем.
 * Первый шаг назван по способу: «Почта», «Телефон» или «Способ» —
 * пока человек его не выбрал.
 */
export function RegisterSteps({
    current,
    method = 'email',
}: {
    current: 1 | 2 | 3;
    method?: 'email' | 'phone' | null;
}) {
    const first =
        method === 'phone' ? 'auth.reg_step_phone' : method === null ? 'auth.reg_step_method' : 'auth.reg_step_email';
    const steps = [t(first), t('auth.reg_step_code'), t('auth.reg_step_details')];

    return (
        <nav aria-label={t('auth.reg_step_of', { current, total: steps.length })} className="mb-6">
            <ol className="flex items-center gap-2">
                {steps.map((label, i) => {
                    const n = i + 1;
                    const done = n < current;
                    const active = n === current;

                    return (
                        <li
                            key={label}
                            className="flex min-w-0 flex-1 items-center gap-2"
                            aria-current={active ? 'step' : undefined}
                        >
                            <span
                                className={cn(
                                    'flex size-7 shrink-0 items-center justify-center rounded-full text-[13px] font-semibold',
                                    done && 'bg-success text-white',
                                    active && 'bg-primary-700 text-white',
                                    !done && !active && 'bg-canvas text-muted',
                                )}
                            >
                                {done ? <Check aria-hidden className="size-4" /> : n}
                            </span>
                            <span
                                className={cn('truncate text-sm', active ? 'font-semibold' : 'text-muted')}
                            >
                                {label}
                            </span>
                            {n < steps.length && <span aria-hidden className="bg-canvas h-px flex-1" />}
                        </li>
                    );
                })}
            </ol>
        </nav>
    );
}
