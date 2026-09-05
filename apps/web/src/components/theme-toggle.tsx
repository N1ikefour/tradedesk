import { Moon, Sun } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { t } from '@/i18n';
import { useTheme } from '@/lib/use-theme';

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const label = theme === 'dark' ? t.theme.switchToLight : t.theme.switchToDark;

  return (
    <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label={label} title={label}>
      {theme === 'dark' ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}
    </Button>
  );
}
