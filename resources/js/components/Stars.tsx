import { Star } from 'lucide-react';
import { useState } from 'react';
import { t } from '@/lib/i18n';

/** Пять звёзд: заполненные до оценки включительно. */
export function Stars({ value, size = 16 }: { value: number; size?: number }) {
    return (
        <span className="row" style={{ gap: 2 }} aria-label={t('reviews.rating_aria', { value })}>
            {[1, 2, 3, 4, 5].map((i) => (
                <Star
                    key={i}
                    aria-hidden
                    style={{ width: size, height: size }}
                    fill={i <= value ? 'var(--warning)' : 'none'}
                    color={i <= value ? 'var(--warning)' : 'var(--border-strong)'}
                />
            ))}
        </span>
    );
}

/** Выбор оценки звёздами — то же управление, что и в чтении. */
export function StarPicker({ value, onChange, label }: { value: number; onChange: (v: number) => void; label: string }) {
    const [hover, setHover] = useState(0);
    const shown = hover || value;

    return (
        <div className="row" style={{ gap: 12, alignItems: 'center', justifyContent: 'space-between' }}>
            <span className="t-sm">{label}</span>
            <span className="row" style={{ gap: 2 }} onMouseLeave={() => setHover(0)}>
                {[1, 2, 3, 4, 5].map((i) => (
                    <button
                        key={i}
                        type="button"
                        aria-label={t('reviews.star_aria', { value: i })}
                        onMouseEnter={() => setHover(i)}
                        onClick={() => onChange(i)}
                        style={{ background: 'none', border: 0, padding: 2, cursor: 'pointer', lineHeight: 0 }}
                    >
                        <Star
                            aria-hidden
                            className="size-5"
                            fill={i <= shown ? 'var(--warning)' : 'none'}
                            color={i <= shown ? 'var(--warning)' : 'var(--border-strong)'}
                        />
                    </button>
                ))}
            </span>
        </div>
    );
}
