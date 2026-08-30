import { AnimatePresence, motion } from "framer-motion";
import type { ReactNode } from "react";
import { useEffect, useId, useRef } from "react";

import { Button } from "./ui";
import { cn, EASE_OUT } from "../lib/utils";

export type MenuItem = {
  label: string;
  icon?: ReactNode;
  danger?: boolean;
  onSelect: () => void;
};

export type MenuState = { x: number; y: number; items: MenuItem[] };

export function ContextMenu({ menu, onClose }: { menu: MenuState | null; onClose: () => void }) {
  useEffect(() => {
    if (!menu) return;
    const close = () => onClose();
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("click", close);
    window.addEventListener("contextmenu", close);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("contextmenu", close);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
      window.removeEventListener("keydown", onKey);
    };
  }, [menu, onClose]);

  return (
    <AnimatePresence>
      {menu && (
        <motion.div
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.96 }}
          transition={{ duration: 0.12, ease: EASE_OUT }}
          style={{
            top: Math.min(menu.y, window.innerHeight - menu.items.length * 36 - 24),
            left: Math.min(menu.x, window.innerWidth - 200),
            transformOrigin: "top left"
          }}
          className="fixed z-50 min-w-44 rounded-md border border-border bg-elevated p-1 elevate-lg"
          onClick={(event) => event.stopPropagation()}
          onContextMenu={(event) => {
            event.preventDefault();
            event.stopPropagation();
          }}
        >
          {menu.items.map((item, index) => (
            <button
              key={index}
              onClick={() => {
                item.onSelect();
                onClose();
              }}
              className={cn(
                "flex w-full items-center gap-2 rounded-sm px-2.5 py-1.5 text-sm transition-colors",
                item.danger
                  ? "text-danger hover:bg-[color-mix(in_oklab,var(--danger)_14%,transparent)]"
                  : "text-foreground hover:bg-muted"
              )}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Delete",
  onConfirm,
  onCancel
}: {
  open: boolean;
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    if (open && !element.open) { element.showModal(); cancel.current?.focus(); }
    else if (!open && element.open) element.close();
  }, [open]);

  return <dialog ref={dialog} aria-labelledby={titleId}
    onCancel={event => { event.preventDefault(); onCancel(); }}
    className="m-auto w-[calc(100%-2rem)] max-w-sm rounded-lg border border-border bg-card p-5 text-foreground shadow-xl backdrop:bg-black/60">
    <h2 id={titleId} className="text-base font-semibold">{title}</h2>
    <div className="mt-2 text-sm text-muted-foreground">{message}</div>
    <div className="mt-5 flex justify-end gap-2">
      <button ref={cancel} className="rounded-md px-3 py-2 text-sm hover:bg-muted focus-visible:outline-2 focus-visible:outline-accent" onClick={onCancel}>Cancel</button>
      <Button variant="danger" onClick={onConfirm}>{confirmLabel}</Button>
    </div>
  </dialog>;
}
