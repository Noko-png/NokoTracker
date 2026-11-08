import { Copy, Download, MoreHorizontal } from "lucide-react";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

export function RecipeActionsMenu({ name, busy, onDuplicate, onExport }: {
  name: string;
  busy: boolean;
  onDuplicate: () => void;
  onExport?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    root.current?.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus();
    function outside(event: PointerEvent) {
      if (event.target instanceof Node && !root.current?.contains(event.target)) setOpen(false);
    }
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);

  function close() {
    setOpen(false);
    trigger.current?.focus();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (!open) return;
    if (event.key === "Escape") {
      event.preventDefault();
      close();
    } else if (event.key === "Tab") {
      close();
    } else if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      const items = Array.from(root.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not(:disabled)') ?? []);
      if (!items.length) return;
      const current = items.indexOf(document.activeElement as HTMLButtonElement);
      const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1
        : (current + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
      items[next]?.focus();
    }
  }

  return (
    <div className="recipe-more" ref={root} onKeyDown={handleKeyDown}>
      <button
        ref={trigger}
        className="icon-button recipe-more-button"
        aria-label={`Weitere Aktionen fuer ${name}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        disabled={busy}
        title="Weitere Aktionen"
        type="button"
        onClick={() => setOpen(current => !current)}
        onKeyDown={event => {
          if (event.key === "ArrowDown" && !open) {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        <MoreHorizontal size={20} />
      </button>
      {open && (
        <div className="recipe-more-menu" role="menu" aria-label={`Aktionen fuer ${name}`} id={menuId}>
          <button role="menuitem" disabled={busy} type="button" onClick={() => { close(); onDuplicate(); }}>
            <Copy size={16} /> Duplizieren
          </button>
          {onExport && <button role="menuitem" disabled={busy} type="button" onClick={() => { close(); onExport(); }}>
            <Download size={16} /> Exportieren
          </button>}
        </div>
      )}
    </div>
  );
}
