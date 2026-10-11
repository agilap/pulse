import { NavLink } from "react-router-dom";

const NAV = [
  { to: "/", label: "Overview", end: true },
  { to: "/monitors", label: "Monitors", end: false },
  { to: "/incidents", label: "Incidents", end: false },
];

export function MobileNav() {
  return (
    <nav
      aria-label="Primary"
      className="flex gap-1 border-b border-line bg-sidebar px-2 py-2 md:hidden"
    >
      {NAV.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) =>
            `flex-1 rounded-md px-2 py-1.5 text-center text-sm ${
              isActive
                ? "bg-raised text-ink font-medium"
                : "text-ink-dim hover:text-ink"
            }`
          }
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}
