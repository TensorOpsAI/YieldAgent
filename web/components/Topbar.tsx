export function Topbar() {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-line px-7">
      <div className="flex items-baseline gap-3">
        <span className="eyebrow">Workspace</span>
        <span className="font-display text-xl leading-none text-ink">
          TensorOps Growth Lab
        </span>
      </div>
      <div className="flex items-center gap-3 text-[14px] text-muted">
        <span className="hidden sm:inline">Owner</span>
        <span className="grid h-7 w-7 place-items-center rounded-full bg-ink text-[13px] font-semibold text-paper">
          T
        </span>
      </div>
    </header>
  );
}
