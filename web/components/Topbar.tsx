export function Topbar() {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-gray-200 bg-white px-6">
      <div>
        <div className="text-[10px] font-medium tracking-wide text-gray-400">
          WORKSPACE
        </div>
        <div className="text-sm font-semibold text-gray-900">
          TensorOps Growth Lab
        </div>
      </div>
      <div className="rounded-full border border-gray-200 px-3 py-1 text-sm text-gray-600">
        Owner
      </div>
    </header>
  );
}
