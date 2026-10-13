import { useEffect, useRef, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import styles from "../App.module.css";

export default function Dialog({
  title,
  onClose,
  children,
  drawer = false,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  drawer?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const { t } = useTranslation();
  useEffect(() => {
    const element = ref.current!;
    const previous = document.activeElement as HTMLElement | null;
    element.showModal();
    return () => {
      element.close();
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className={drawer ? styles.drawer : styles.dialog}
      aria-label={title}
      onCancel={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <header className={styles.dialogHeader}>
        <h2>{title}</h2>
        <button onClick={onClose} aria-label={t("ws_close")}>
          ×
        </button>
      </header>
      {children}
    </dialog>
  );
}
