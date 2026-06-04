const CONNECTIONS = [
  { platform: "LinkedIn Ads", status: "Connected", detail: "Gad Benram" },
  { platform: "Meta Ads", status: "Disabled", detail: "Provider setup required" },
  { platform: "Google Ads", status: "Disabled", detail: "Provider setup required" },
];

export default function Connections() {
  return (
    <div className="grid grid-cols-3 gap-4 p-6">
      {CONNECTIONS.map((c) => (
        <div
          key={c.platform}
          className="rounded-xl border border-gray-200 bg-white p-4"
        >
          <div className="font-medium text-gray-900">{c.platform}</div>
          <div
            className={`mt-1 text-sm ${
              c.status === "Connected" ? "text-emerald-600" : "text-gray-400"
            }`}
          >
            {c.status}
          </div>
          <div className="mt-1 text-xs text-gray-400">{c.detail}</div>
        </div>
      ))}
    </div>
  );
}
