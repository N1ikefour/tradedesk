/**
 * Регрессия на само правило `no-restricted-syntax` из `eslint.config.js` (X-15).
 *
 * Конфиг подаётся ESLint файлом с диска (`overrideConfigFile`), а не копией селектора
 * рядом с тестом: копия со временем разошлась бы с оригиналом и продолжила бы зеленеть
 * на сломанном правиле. Здесь проверяется настоящее правило настоящим парсером.
 */
import path from 'node:path';

import { ESLint, type Linter } from 'eslint';
import { beforeAll, describe, expect, it } from 'vitest';

const RULE_ID = 'no-restricted-syntax';

const WEB_ROOT = path.resolve(import.meta.dirname, '../..');
const CONFIG_FILE = path.join(WEB_ROOT, 'eslint.config.js');
// Файла на диске нет и не нужно: путь ESLint использует только чтобы выбрать блок правил
// по `files`. Расширение `.tsx` обязательно — иначе фикстура не разберётся как JSX.
const FIXTURE_FILE = path.join(WEB_ROOT, 'src/button-type-fixture.tsx');

let eslint: ESLint;

beforeAll(() => {
  eslint = new ESLint({ cwd: WEB_ROOT, overrideConfigFile: CONFIG_FILE });
});

/**
 * Отдаёт только нарушения нашего правила. Если в `no-restricted-syntax` добавят второй
 * селектор, фильтр придётся сузить: иначе чужое нарушение зачтётся за наше.
 */
async function lintJsx(jsx: string): Promise<Linter.LintMessage[]> {
  const [result] = await eslint.lintText(`export const Fixture = () => ${jsx};\n`, {
    filePath: FIXTURE_FILE,
  });
  if (!result) {
    throw new Error('ESLint не вернул результат для фикстуры');
  }
  return result.messages.filter((message) => message.ruleId === RULE_ID);
}

describe('eslint: кнопка обязана объявить type', () => {
  it('ловит <Button> без типа', async () => {
    await expect(lintJsx('<Button>x</Button>')).resolves.toHaveLength(1);
  });

  it('ловит строчный <button> без типа', async () => {
    await expect(lintJsx('<button>x</button>')).resolves.toHaveLength(1);
  });

  it('ловит <Button> со спредом, но без типа', async () => {
    await expect(lintJsx('<Button {...props} />')).resolves.toHaveLength(1);
  });

  it('пропускает объявленный type в обоих написаниях и вместе со спредом', async () => {
    await expect(lintJsx('<Button type="button">x</Button>')).resolves.toHaveLength(0);
    await expect(lintJsx('<Button type="submit">x</Button>')).resolves.toHaveLength(0);
    await expect(lintJsx('<button type="button">x</button>')).resolves.toHaveLength(0);
    await expect(lintJsx('<Button {...props} type="button" />')).resolves.toHaveLength(0);
  });

  it('пропускает asChild: Slot рендерит ребёнка, <button> в DOM не появляется', async () => {
    await expect(lintJsx('<Button asChild><a href="/x">x</a></Button>')).resolves.toHaveLength(0);
  });

  // Тот случай, ради которого в селекторе стоит комбинатор `>`: `type` у вложенного JSX
  // внутри значения чужого атрибута — не тип кнопки. Убери `>` — этот тест обязан упасть.
  it('ловит <Button> без типа, когда type есть у вложенного JSX', async () => {
    await expect(lintJsx('<Button title={<Icon type="warn" />}>x</Button>')).resolves.toHaveLength(
      1,
    );
  });

  it('пропускает <Button> с типом, у которого вложенный JSX тоже имеет type', async () => {
    await expect(
      lintJsx('<Button type="button" title={<Icon type="warn" />}>x</Button>'),
    ).resolves.toHaveLength(0);
  });
});
