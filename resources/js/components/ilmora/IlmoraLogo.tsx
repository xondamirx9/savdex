import '@fontsource/cormorant-garamond/latin-400.css';
import { cn } from '@/lib/cn';

/**
 * Знак ILMORA текстом, без картинки: буква «I» в квадрате и слово
 * «ILMORA» шрифтом Cormorant Garamond. Цвета — ILMORA (ilmora.css),
 * поэтому знак одинаков и на тёмной панели Savdex, и на своей.
 */
export function IlmoraLogo({ className, compact = false }: { className?: string; compact?: boolean }) {
    return (
        <span className={cn('ilmora-logo', compact && 'ilmora-logo--compact', className)}>
            <span className="ilmora-logo__mark" aria-hidden>
                I
            </span>
            <span className="ilmora-logo__word">ILMORA</span>
        </span>
    );
}
