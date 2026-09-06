import { useState, type FormEvent } from 'react';

import { messageForError } from '@/api/error-message';
import { useArchiveAccount, useDeleteAccount, type Account } from '@/accounts/api';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Modal } from '@/components/ui/modal';
import { t } from '@/i18n';

/**
 * Архивирование и удаление — две разные потери, и человек должен видеть, чем они
 * отличаются, до того как выберет. Обе кнопки живут рядом именно поэтому: архив назван
 * альтернативой прямо в окне удаления, но выбрать его можно только если он на виду.
 */
export function DangerActions({
  account,
  onDeleted,
}: {
  account: Account;
  onDeleted?: () => void;
}) {
  const [dialog, setDialog] = useState<'archive' | 'delete' | null>(null);

  return (
    <>
      {account.status === 'archived' ? null : (
        <Button type="button" variant="ghost" size="sm" onClick={() => setDialog('archive')}>
          {t.accounts.archive}
        </Button>
      )}
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="text-destructive hover:bg-destructive/10 hover:text-destructive"
        onClick={() => setDialog('delete')}
      >
        {t.accounts.delete}
      </Button>

      <ArchiveDialog
        account={account}
        open={dialog === 'archive'}
        onClose={() => setDialog(null)}
      />
      <DeleteDialog
        account={account}
        open={dialog === 'delete'}
        onClose={() => setDialog(null)}
        onDeleted={onDeleted}
      />
    </>
  );
}

function ArchiveDialog({
  account,
  open,
  onClose,
}: {
  account: Account;
  open: boolean;
  onClose: () => void;
}) {
  const archive = useArchiveAccount(account.id);

  const close = () => {
    archive.reset();
    onClose();
  };

  return (
    <Modal open={open} onClose={close} title={t.accounts.archiveTitle(account.label)}>
      <div className="flex flex-col gap-4">
        <p className="text-sm">{t.accounts.archiveBody}</p>
        <Alert variant="warning">{t.accounts.archiveIrreversible}</Alert>

        {archive.isError ? (
          <Alert variant="destructive">
            {t.accounts.archiveFailed} {messageForError(archive.error)}
          </Alert>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            disabled={archive.isPending}
            onClick={() => archive.mutate(undefined, { onSuccess: close })}
          >
            {archive.isPending ? t.accounts.archiving : t.accounts.archiveConfirm}
          </Button>
          {/* «Отмена» закрывает окно и ничего не отправляет. */}
          <Button type="button" variant="ghost" disabled={archive.isPending} onClick={close}>
            {t.common.cancel}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

/**
 * `DELETE` уносит каскадом сделки, позиции, записи журнала и рефлексии. Подтверждение
 * вводом имени (SPEC.md 9.3) стоит здесь не как замок, а как пауза: перепечатать слово
 * несложно, поэтому перед полем перечислено, что именно исчезает, — иначе человек
 * подтвердит ровно то, чего не понял.
 */
function DeleteDialog({
  account,
  open,
  onClose,
  onDeleted,
}: {
  account: Account;
  open: boolean;
  onClose: () => void;
  onDeleted?: () => void;
}) {
  const [typed, setTyped] = useState('');
  const [mismatch, setMismatch] = useState(false);
  const remove = useDeleteAccount(account.id);

  const close = () => {
    setTyped('');
    setMismatch(false);
    remove.reset();
    onClose();
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (remove.isPending) {
      return;
    }
    if (typed.trim() !== account.label.trim()) {
      setMismatch(true);
      return;
    }
    remove.mutate(undefined, {
      onSuccess: () => {
        close();
        onDeleted?.();
      },
    });
  };

  return (
    <Modal open={open} onClose={close} title={t.accounts.deleteTitle(account.label)}>
      <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
        <div className="flex flex-col gap-2">
          <p className="text-sm">{t.accounts.deleteLead}</p>
          <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            <li>{t.accounts.deleteLossDeals}</li>
            <li>{t.accounts.deleteLossPositions(account.positions_count)}</li>
            <li>{t.accounts.deleteLossJournal}</li>
            <li>{t.accounts.deleteLossReflections}</li>
            <li>{t.accounts.deleteLossAttachments}</li>
            <li>{t.accounts.deleteLossHistory}</li>
          </ul>
        </div>

        <Alert>{t.accounts.deleteAlternative}</Alert>

        <Field
          id="account-delete-confirm"
          label={t.accounts.deleteConfirmLabel(account.label)}
          error={mismatch ? t.accounts.deleteConfirmMismatch : null}
        >
          {(props) => (
            <Input
              {...props}
              value={typed}
              placeholder={t.accounts.deleteConfirmPlaceholder}
              autoComplete="off"
              onChange={(event) => {
                setTyped(event.target.value);
                setMismatch(false);
              }}
            />
          )}
        </Field>

        {remove.isError ? (
          <Alert variant="destructive">
            {t.accounts.deleteFailed} {messageForError(remove.error)}
          </Alert>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="submit"
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            disabled={remove.isPending}
          >
            {remove.isPending ? t.accounts.deleting : t.accounts.deleteConfirm}
          </Button>
          <Button type="button" variant="ghost" disabled={remove.isPending} onClick={close}>
            {t.common.cancel}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
