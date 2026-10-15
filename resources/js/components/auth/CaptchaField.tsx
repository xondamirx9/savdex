import { AlertCircle, Check, RefreshCw, ShieldCheck, X } from 'lucide-react';
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { cn } from '@/lib/cn';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';

type Challenge = { image: string; length: number };
type State = 'idle' | 'checking' | 'open' | 'verifying' | 'verified';

const JSON_HEADERS = { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' };

/** Токен CSRF из куки XSRF-TOKEN — как у автосохранения мастера объявлений. */
function xsrf(): Record<string, string> {
    const token = document.cookie.match(/XSRF-TOKEN=([^;]+)/)?.[1];

    return token ? { 'X-XSRF-TOKEN': decodeURIComponent(token) } : {};
}

/**
 * Капча, как у Google: галочка «Я не робот», по ней — окно с картинкой из
 * букв и цифр (savdex/web/captcha.py). Окно само проверяет введённое
 * (POST /captcha/verify) и получает одноразовый пропуск — он и уходит с
 * формой в поле captcha. Пропуск гасится при отправке формы, поэтому после
 * каждой отправки страница меняет reloadKey и галочка снимается.
 */
export function CaptchaField({
    purpose,
    value,
    onChange,
    error,
    reloadKey = 0,
}: {
    purpose: 'register';
    /** Пропуск после пройденной проверки; пусто — галочки нет. */
    value: string;
    onChange: (token: string) => void;
    error?: string;
    reloadKey?: number;
}) {
    const [state, setState] = useState<State>(value ? 'verified' : 'idle');
    const [challenge, setChallenge] = useState<Challenge | null>(null);
    const [loadingImage, setLoadingImage] = useState(false);
    const [typed, setTyped] = useState('');
    const [problem, setProblem] = useState<string | null>(null);
    const request = useRef(0);
    const root = useRef<HTMLDivElement>(null);
    const input = useRef<HTMLInputElement>(null);
    // onChange от useForm меняется на каждой отрисовке — держим последний
    const change = useRef(onChange);
    change.current = onChange;
    const ids = useId();
    const popupId = `${ids}-popup`;
    const errorId = `${ids}-error`;
    const isOpen = state === 'open' || state === 'verifying';

    const load = useCallback(async (): Promise<boolean> => {
        const id = ++request.current;
        setLoadingImage(true);
        setTyped('');

        try {
            const res = await fetch(`${routes.captcha}?for=${purpose}`, {
                // X-Requested-With: иначе сессия запомнила бы /captcha как
                // «предыдущую страницу», и ошибка формы уводила бы на него
                headers: JSON_HEADERS,
                cache: 'no-store',
            });

            if (!res.ok) throw new Error(String(res.status));

            const data: Challenge = await res.json();

            if (id !== request.current) return false;

            setChallenge(data);

            return true;
        } catch {
            if (id === request.current) setProblem(t('captcha.load_failed'));

            return false;
        } finally {
            if (id === request.current) setLoadingImage(false);
        }
    }, [purpose]);

    const close = useCallback(() => {
        request.current++;
        setState('idle');
        setProblem(null);
        setChallenge(null);
    }, []);

    async function tick() {
        if (state !== 'idle') return;

        setProblem(null);
        setState('checking');

        if (await load()) {
            setState('open');
        } else {
            setState('idle');
        }
    }

    async function confirm(e: { preventDefault(): void; stopPropagation(): void }) {
        e.preventDefault();
        // Окно — не вложенная форма: Enter в поле не должен отправить форму входа
        e.stopPropagation();

        if (typed.trim() === '') {
            setProblem(t('captcha.errors.required'));
            input.current?.focus();
            return;
        }

        setState('verifying');

        try {
            const res = await fetch(`${routes.captchaVerify}?for=${purpose}`, {
                method: 'POST',
                headers: { ...JSON_HEADERS, 'Content-Type': 'application/json', ...xsrf() },
                body: JSON.stringify({ captcha: typed }),
            });
            const data: { token?: string; message?: string } = await res.json().catch(() => ({}));

            if (res.ok && data.token) {
                change.current(data.token);
                setProblem(null);
                setChallenge(null);
                setState('verified');
                return;
            }

            // Неверно или картинка устарела: она уже погашена — нужна новая
            setProblem(data.message ?? t('captcha.load_failed'));
        } catch {
            setProblem(t('captcha.load_failed'));
        }

        setState('open');
        await load();
        input.current?.focus();
    }

    // Отправка формы гасит пропуск: галочку снимаем
    const first = useRef(true);
    useEffect(() => {
        if (first.current) {
            first.current = false;
            return;
        }

        close();
        change.current('');
    }, [reloadKey, close]);

    // Окно закрывается по Esc и по щелчку мимо
    useEffect(() => {
        if (!isOpen) return;

        input.current?.focus();

        function onKey(e: KeyboardEvent) {
            if (e.key === 'Escape') close();
        }

        function onDown(e: MouseEvent) {
            if (root.current && !root.current.contains(e.target as Node)) close();
        }

        document.addEventListener('keydown', onKey);
        document.addEventListener('mousedown', onDown);

        return () => {
            document.removeEventListener('keydown', onKey);
            document.removeEventListener('mousedown', onDown);
        };
    }, [isOpen, close]);

    const verified = state === 'verified';

    return (
        <div ref={root} className="relative">
            <div
                className={cn(
                    'border-line bg-canvas flex h-[74px] w-full max-w-[304px] items-center justify-between gap-3 rounded-[4px] border pr-2.5 pl-3 shadow-sm',
                    error && !verified && 'border-danger',
                )}
            >
                <button
                    type="button"
                    role="checkbox"
                    aria-checked={verified}
                    aria-expanded={isOpen}
                    aria-controls={isOpen ? popupId : undefined}
                    aria-describedby={error && !verified ? errorId : undefined}
                    onClick={() => void tick()}
                    disabled={state === 'checking' || verified}
                    className="group flex min-w-0 items-center gap-3 text-left"
                >
                    <span
                        className={cn(
                            'grid size-7 shrink-0 place-items-center rounded-[3px] transition-colors',
                            state === 'idle' &&
                                'border-line-strong bg-surface group-hover:border-muted border-2',
                            isOpen && 'border-primary-500 bg-surface border-2',
                        )}
                        aria-hidden
                    >
                        {state === 'checking' && (
                            <span className="border-primary-500 size-6 animate-spin rounded-full border-[3px] border-t-transparent" />
                        )}
                        {verified && <Check className="text-success size-8" strokeWidth={3} />}
                    </span>
                    <span className="text-ink text-[14px] leading-tight">
                        {verified ? t('captcha.verified') : t('captcha.checkbox')}
                    </span>
                </button>

                <span className="text-muted flex shrink-0 flex-col items-center gap-0.5 text-[10px] leading-none" aria-hidden>
                    <ShieldCheck className="text-primary-700 size-7" strokeWidth={1.75} />
                    SavDex
                </span>
            </div>

            {error && !verified && (
                <p id={errorId} className="text-danger mt-1.5 flex items-start gap-1.5 text-[13px]">
                    <AlertCircle aria-hidden className="mt-0.5 size-3.5 shrink-0" />
                    <span>{error}</span>
                </p>
            )}

            {isOpen && (
                <div
                    id={popupId}
                    role="dialog"
                    aria-label={t('captcha.popup_title')}
                    className="border-line bg-surface absolute top-full left-0 z-30 mt-2 w-[320px] max-w-[calc(100vw-32px)] overflow-hidden rounded-[6px] border shadow-xl"
                >
                    <div className="bg-primary-700 flex items-start justify-between gap-2 px-4 py-3 text-white">
                        <p className="text-[15px] leading-snug font-medium">{t('captcha.popup_title')}</p>
                        <button
                            type="button"
                            onClick={close}
                            aria-label={t('captcha.close')}
                            className="-mt-1 -mr-2 grid size-8 shrink-0 place-items-center rounded-full text-white/80 hover:bg-white/15 hover:text-white"
                        >
                            <X aria-hidden className="size-4" />
                        </button>
                    </div>

                    {/* div, а не form: форма в форме — недопустимый HTML */}
                    <div
                        className="space-y-3 p-4"
                        onKeyDown={(e) => {
                            if (e.key === 'Enter') void confirm(e);
                        }}
                    >
                        {/* Картинка светлая в любой теме: фон под ней — её же бумага */}
                        <div className="border-line aspect-[200/64] w-full overflow-hidden rounded-[4px] border bg-white">
                            {challenge && !loadingImage ? (
                                <img
                                    src={challenge.image}
                                    alt={t('captcha.image_alt')}
                                    width={200}
                                    height={64}
                                    draggable={false}
                                    className="size-full select-none"
                                />
                            ) : (
                                <span className="block size-full animate-pulse bg-slate-100" aria-label={t('captcha.loading')} />
                            )}
                        </div>

                        <input
                            ref={input}
                            type="text"
                            aria-label={t('captcha.label')}
                            aria-invalid={problem ? true : undefined}
                            autoComplete="off"
                            autoCapitalize="characters"
                            autoCorrect="off"
                            spellCheck={false}
                            maxLength={(challenge?.length ?? 5) + 4}
                            placeholder={t('captcha.placeholder')}
                            value={typed}
                            onChange={(e) => {
                                setTyped(e.target.value);
                                if (problem) setProblem(null);
                            }}
                            className={cn(
                                'bg-surface border-line rounded-btn focus:border-primary-500 focus:ring-primary-500/15 h-11 w-full border px-3.5 text-[15px] focus:ring-3 focus:outline-none',
                                problem && 'border-danger',
                            )}
                        />

                        {problem && (
                            <p className="text-danger flex items-start gap-1.5 text-[13px]" role="alert">
                                <AlertCircle aria-hidden className="mt-0.5 size-3.5 shrink-0" />
                                <span>{problem}</span>
                            </p>
                        )}
                    </div>

                    <div className="border-line flex items-center justify-between gap-2 border-t px-2 py-2">
                        <button
                            type="button"
                            onClick={() => {
                                setProblem(null);
                                void load();
                            }}
                            disabled={loadingImage || state === 'verifying'}
                            title={t('captcha.refresh')}
                            aria-label={t('captcha.refresh')}
                            className="text-muted hover:text-ink hover:bg-canvas rounded-btn grid size-10 place-items-center transition-colors disabled:opacity-50"
                        >
                            <RefreshCw aria-hidden className={cn('size-[18px]', loadingImage && 'animate-spin')} />
                        </button>
                        <button
                            type="button"
                            onClick={(e) => void confirm(e)}
                            disabled={loadingImage || state === 'verifying'}
                            className="bg-primary-700 hover:bg-primary-600 rounded-btn h-10 px-5 text-sm font-semibold text-white disabled:opacity-60"
                        >
                            {state === 'verifying' ? t('captcha.checking') : t('captcha.confirm')}
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
