import { AlertCircle, Check, RefreshCw } from 'lucide-react';
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { cn } from '@/lib/cn';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';

type Challenge = { target: string; grid: number; tiles: string[] };

/**
 * Капча из картинок: «отметьте все светофоры» (переходы, витрины).
 * Задание выдаёт сервер (GET /captcha, savdex/web/captcha.py) и проверяет
 * его один раз — верно или нет, оно гасится. Поэтому после каждой
 * отправки формы нужно новое: страница меняет reloadKey, и сетка
 * перезагружается, а отмеченное сбрасывается.
 */
export function CaptchaGrid({
    purpose,
    value,
    onChange,
    error,
    reloadKey = 0,
}: {
    purpose: 'login' | 'register' | 'ilmora';
    value: number[];
    onChange: (cells: number[]) => void;
    error?: string;
    reloadKey?: number;
}) {
    const [challenge, setChallenge] = useState<Challenge | null>(null);
    const [state, setState] = useState<'loading' | 'ready' | 'failed'>('loading');
    const request = useRef(0);
    // onChange от useForm меняется на каждой отрисовке — держим последний
    const change = useRef(onChange);
    change.current = onChange;
    const errorId = `${useId()}-error`;

    const load = useCallback(async () => {
        const id = ++request.current;
        setState('loading');
        change.current([]);

        try {
            const res = await fetch(`${routes.captcha}?for=${purpose}`, {
                // X-Requested-With: иначе сессия запомнила бы /captcha как
                // «предыдущую страницу», и ошибка формы уводила бы на него
                headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                cache: 'no-store',
            });

            if (!res.ok) throw new Error(String(res.status));

            const data: Challenge = await res.json();

            if (id !== request.current) return;

            setChallenge(data);
            setState('ready');
        } catch {
            if (id === request.current) setState('failed');
        }
    }, [purpose]);

    useEffect(() => {
        void load();
    }, [load, reloadKey]);

    function toggle(cell: number) {
        onChange(value.includes(cell) ? value.filter((c) => c !== cell) : [...value, cell].sort((a, b) => a - b));
    }

    const cells = challenge ? challenge.grid * challenge.grid : 9;

    return (
        <fieldset aria-describedby={error ? errorId : undefined}>
            <legend className="mb-2 text-sm">
                {t('captcha.prompt')}{' '}
                {challenge && state === 'ready' && (
                    <strong className="font-semibold">{t(`captcha.targets.${challenge.target}`)}</strong>
                )}
            </legend>

            <div
                className={cn(
                    'rounded-btn border-line bg-surface border p-1.5',
                    error && 'border-danger',
                )}
            >
                {state === 'failed' ? (
                    <div className="text-muted flex aspect-square flex-col items-center justify-center gap-3 text-sm">
                        <span>{t('captcha.load_failed')}</span>
                        <button
                            type="button"
                            onClick={() => void load()}
                            className="text-primary-700 font-medium hover:underline"
                        >
                            {t('captcha.retry')}
                        </button>
                    </div>
                ) : (
                    <div className="grid grid-cols-3 gap-1.5" aria-busy={state === 'loading'}>
                        {Array.from({ length: cells }, (_, i) => {
                            const src = state === 'ready' ? challenge?.tiles[i] : undefined;
                            const picked = value.includes(i);

                            if (!src) {
                                return (
                                    <div
                                        key={i}
                                        className="bg-canvas aspect-square animate-pulse rounded-[6px]"
                                        aria-hidden
                                    />
                                );
                            }

                            return (
                                <button
                                    key={i}
                                    type="button"
                                    aria-pressed={picked}
                                    aria-label={t('captcha.tile', { n: i + 1 })}
                                    onClick={() => toggle(i)}
                                    className="focus-visible:ring-primary-500 relative aspect-square overflow-hidden rounded-[6px] focus:outline-none focus-visible:ring-3"
                                >
                                    <img
                                        src={src}
                                        alt=""
                                        draggable={false}
                                        className={cn(
                                            'size-full object-cover transition-transform duration-150 select-none',
                                            picked && 'scale-[0.82]',
                                        )}
                                    />
                                    {picked && (
                                        <span className="bg-primary-700 absolute top-1 left-1 grid size-6 place-items-center rounded-full text-white shadow">
                                            <Check aria-hidden className="size-4" strokeWidth={3} />
                                        </span>
                                    )}
                                </button>
                            );
                        })}
                    </div>
                )}

                <div className="mt-1.5 flex items-center justify-between gap-2 px-0.5">
                    <span className="text-muted text-xs">
                        {state === 'loading' ? t('captcha.loading') : t('captcha.hint')}
                    </span>
                    <button
                        type="button"
                        onClick={() => void load()}
                        disabled={state === 'loading'}
                        title={t('captcha.refresh')}
                        aria-label={t('captcha.refresh')}
                        className="text-muted hover:text-ink hover:bg-canvas rounded-btn grid size-9 shrink-0 place-items-center transition-colors disabled:opacity-50"
                    >
                        <RefreshCw aria-hidden className={cn('size-4', state === 'loading' && 'animate-spin')} />
                    </button>
                </div>
            </div>

            {error && (
                <p id={errorId} className="text-danger mt-1.5 flex items-start gap-1.5 text-[13px]">
                    <AlertCircle aria-hidden className="mt-0.5 size-3.5 shrink-0" />
                    <span>{error}</span>
                </p>
            )}
        </fieldset>
    );
}
