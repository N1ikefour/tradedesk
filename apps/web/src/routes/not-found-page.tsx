import { Link } from 'react-router';

import { Button } from '@/components/ui/button';
import { t } from '@/i18n';

export function NotFoundPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-4 text-center">
      <h1 className="text-2xl font-semibold tracking-tight">{t.pages.notFound}</h1>
      <p className="text-sm text-muted-foreground">{t.pages.notFoundHint}</p>
      <Button asChild variant="outline">
        <Link to="/">{t.pages.goHome}</Link>
      </Button>
    </div>
  );
}
