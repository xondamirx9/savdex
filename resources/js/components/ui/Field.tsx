import { AlertCircle, Eye, EyeOff } from 'lucide-react';
import { useId, useState, type InputHTMLAttributes, type ReactNode } from 'react';
import { cn } from '@/lib/cn';

interface FieldProps {
    label: string;
    /** Сообщение об ошибке с сервера или из клиентской проверки. */
    error?: string;
    /** Подсказка под полем. Скрывается, когда есть ошибка, — иначе шум. */
    hint?: ReactNode;
    required?: boolean;
    children: (attrs: {
        id: string;
        'aria-invalid': boolean | undefined;
        'aria-describedby': string | undefined;
        className: string;
    }) => ReactNode;
}

const INPUT_BASE =
    'w-full h-11 px-3.5 bg-surface border border-line rounded-btn text-[15px] ' +
    'transition-[border-color,box-shadow] duration-150 ' +
    'placeholder:text-slate-400 hover:border-line-strong ' +
    'focus:outline-none focus:border-primary-500 focus:ring-3 focus:ring-primary-500/15 ' +
    'disabled:bg-canvas disabled:text-muted disabled:cursor-not-allowed';

const INPUT_ERROR = 'border-danger focus:border-danger focus:ring-danger/15';

/**
 * Обёртка поля формы.
 *
 * Реализует правила 2–4 из §1 QA.md:
 * — ошибка рядом с полем, а не только сверху страницы;
 * — ошибка передаётся цветом, иконкой и текстом одновременно,
 *   потому что 8 % мужчин не различают красный и зелёный;
 * — поле связано с сообщением через aria-describedby и aria-invalid,
 *   иначе скринридер об ошибке молчит.
 */
export function Field({ label, error, hint, required, children }: FieldProps) {
    const id = useId();
    const errorId = `${id}-error`;
    const hintId = `${id}-hint`;

    return (
        <div className="block">
            <label htmlFor={id} className="mb-1.5 block text-sm font-medium">
                {label}
                {required && (
                    <span className="text-danger" aria-hidden>
                        {' '}
                        *
                    </span>
                )}
            </label>

            {children({
                id,
                'aria-invalid': error ? true : undefined,
                'aria-describedby': error ? errorId : hint ? hintId : undefined,
                className: cn(INPUT_BASE, error && INPUT_ERROR),
            })}

            {error ? (
                <p id={errorId} className="text-danger mt-1.5 flex items-start gap-1.5 text-[13px]">
                    <AlertCircle aria-hidden className="mt-0.5 size-3.5 shrink-0" />
                    <span>{error}</span>
                </p>
            ) : hint ? (
                <p id={hintId} className="text-muted mt-1.5 text-[13px]">
                    {hint}
                </p>
            ) : null}
        </div>
    );
}

type TextInputProps = InputHTMLAttributes<HTMLInputElement> & {
    label: string;
    error?: string;
    hint?: ReactNode;
};

export function TextInput({ label, error, hint, required, ...rest }: TextInputProps) {
    return (
        <Field label={label} error={error} hint={hint} required={required}>
            {(attrs) => <input {...attrs} required={required} {...rest} />}
        </Field>
    );
}

/**
 * Поле пароля с переключателем видимости.
 * Без него человек не может проверить, что набрал, и упирается
 * в «неверный пароль» из-за незамеченной раскладки или Caps Lock.
 */
export function PasswordInput({ label, error, hint, required, ...rest }: TextInputProps) {
    const [visible, setVisible] = useState(false);

    return (
        <Field label={label} error={error} hint={hint} required={required}>
            {(attrs) => (
                <div className="relative">
                    <input
                        {...attrs}
                        {...rest}
                        required={required}
                        type={visible ? 'text' : 'password'}
                        className={cn(attrs.className, 'pr-12')}
                    />
                    <button
                        type="button"
                        onClick={() => setVisible((v) => !v)}
                        aria-label={visible ? 'Скрыть пароль' : 'Показать пароль'}
                        aria-pressed={visible}
                        className="text-muted hover:text-ink hover:bg-canvas rounded-btn absolute top-1/2 right-1 grid size-10 -translate-y-1/2 place-items-center transition-colors"
                    >
                        {visible ? <EyeOff aria-hidden className="size-5" /> : <Eye aria-hidden className="size-5" />}
                    </button>
                </div>
            )}
        </Field>
    );
}
