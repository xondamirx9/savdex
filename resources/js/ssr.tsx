import { createInertiaApp } from '@inertiajs/react';
import createServer from '@inertiajs/react/server';
import { renderToString } from 'react-dom/server';
import { resolvePage } from '@/lib/pages';

const appName = 'SAVDEX';

createServer((page) =>
    createInertiaApp({
        page,
        render: renderToString,
        title: (title) => (title ? `${title} · ${appName}` : appName),
        resolve: resolvePage,
        setup: ({ App, props }) => <App {...props} />,
    }),
);
