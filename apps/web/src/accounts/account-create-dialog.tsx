/**
 * Заведение счёта из переключателя в шапке (`S2-11`, SPEC.md 9.2).
 *
 * Форма — та же самая, что на `/accounts`: подсказка про инвесторский пароль и стирание
 * пароля из состояния и из кэша мутаций существуют в одном экземпляре, копия разошлась бы
 * с оригиналом на первой же правке.
 *
 * Копией не является другое — то, что человек видит после успеха. На `/accounts` окно
 * просто закрывается: новая карточка появляется в списке под ним, и вопроса «что
 * произошло» не возникает. Из шапки человек заводит счёт, стоя на дашборде или в журнале,
 * и там под окном нет ничего, что бы ему ответило. А произошло многое: пароль зашифрован
 * и уехал на сервер, счёт попал в задания коллектору, но сделок у него не будет до
 * первого синка — и в текущий выбор счетов он мог не войти вовсе. Поэтому окно не
 * закрывается молча, а называет всё это и предлагает два продолжения: посмотреть, как
 * счёт подключается, или переключить на него выбор.
 *
 * Выбор счетов при этом не меняется сам: это настройка рабочего места, и человек,
 * смотрящий один счёт из четырёх, не должен обнаружить, что его переставили.
 */
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router';

import { useAccounts, type Account } from '@/accounts/api';
import { AccountForm } from '@/accounts/account-form';
import {
  coversNewAccount,
  useAccountSelection,
  useAccountSelectionStore,
} from '@/accounts/selection';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/ui/modal';
import { t } from '@/i18n';

export function AccountCreateDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [created, setCreated] = useState<Account | null>(null);

  const close = () => {
    setCreated(null);
    onClose();
  };

  return (
    <Modal
      open={open}
      onClose={close}
      title={created === null ? t.accounts.formCreateTitle : t.accountSwitcher.createdTitle}
      className="max-w-xl"
    >
      {/* Форма пересоздаётся при каждом открытии: прошлый ввод, включая пароль, не должен
          пережить закрытие окна. */}
      {open && created === null ? <AccountForm onDone={setCreated} onCancel={close} /> : null}
      {created === null ? null : <CreatedPanel account={created} onClose={close} />}
    </Modal>
  );
}

function CreatedPanel({ account, onClose }: { account: Account; onClose: () => void }) {
  const accounts = useAccounts(false);
  const selection = useAccountSelection();
  const selectIds = useAccountSelectionStore((state) => state.selectIds);
  const covered = coversNewAccount(selection, accounts.data?.items ?? [], account);
  const panel = useRef<HTMLDivElement | null>(null);

  // Кнопка «Добавить», на которой стоял фокус, исчезает вместе с формой, и фокус
  // достаётся `body`: клавиатура начинает обход страницы заново, а сказанное здесь
  // экранный диктор не читает вовсе. Фокус уводится на сам текст, а не на кнопку, —
  // человек пришёл сюда за ответом, а не за следующим действием.
  useEffect(() => {
    panel.current?.focus();
  }, []);

  return (
    <div ref={panel} tabIndex={-1} className="flex flex-col gap-4 outline-none">
      <p className="text-sm">{t.accountSwitcher.createdLead(account.label)}</p>
      <p className="text-sm text-muted-foreground">
        {account.platform === 'mt5'
          ? t.accountSwitcher.createdMt5
          : t.accountSwitcher.createdManual}
      </p>
      <p className="text-sm text-muted-foreground">
        {covered ? t.accountSwitcher.createdInSelection : t.accountSwitcher.createdOutOfSelection}
      </p>

      <div className="flex flex-wrap items-center gap-3">
        <Button asChild>
          <Link to={`/accounts/${account.id}`} onClick={onClose}>
            {t.accountSwitcher.createdOpen}
          </Link>
        </Button>
        {covered ? null : (
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              selectIds([account.id]);
              onClose();
            }}
          >
            {t.accountSwitcher.createdSelectIt}
          </Button>
        )}
        <Button type="button" variant="ghost" onClick={onClose}>
          {t.common.close}
        </Button>
      </div>
    </div>
  );
}
