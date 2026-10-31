import { NavLink } from "react-router-dom";

const NAV = [
  { to: "/", label: "Overview", end: true },
  { to: "/monitors", label: "Monitors", end: false },
  { to: "/incidents", label: "Incidents", end: false },
  { to: "/webhooks", label: "Webhooks", end: false },
];

function PulseMark() {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
      <rect width="22" height="22" rx="5" fill="var(--color-accent)" />
      <path
        d="M3 12h3.2l1.6-4 2.4 8 2.2-6 1.4 2H19"
        stroke="var(--color-app)"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Sidebar() {
  return (
    <aside className="hidden w-56 shrink-0 flex-col border-r border-line bg-sidebar md:flex">
      <div className="flex items-center gap-2 px-4 py-4">
        <PulseMark />
        <span className="text-sm font-semibold tracking-tight text-ink">Pulse</span>
      </div>
      <nav className="flex flex-col gap-0.5 px-2 py-2" aria-label="Primary">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) => {
              const active = isActive
                ? "bg-raised text-ink font-medium"
                : "text-ink-dim hover:bg-raised/60 hover:text-ink";
              return "rounded-md px-2.5 py-1.5 text-sm transition-colors " + active;
            }}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto border-t border-line-soft px-4 py-3">
        <div className="flex items-center gap-2 text-xs text-ink-faint">
          <span className="inline-block size-1.5 rounded-full bg-up" aria-hidden="true" />
          <span>All systems operational</span>
        </div>
      </div>
    </aside>
  );
}
