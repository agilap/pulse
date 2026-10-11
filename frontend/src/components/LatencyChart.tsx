import { useId, useState } from "react";
import type { LatencyPoint } from "../domain/series";
import { fmtDateTime, fmtMs } from "../domain/format";

export function LatencyChart({
  points,
  height = 160,
}: {
  points: LatencyPoint[];
  height?: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const gradientId = useId();

  if (points.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-dashed border-line text-sm text-ink-dim"
        style={{ height }}
      >
        No successful checks to chart yet.
      </div>
    );
  }

  const width = 600;
  const padX = 8;
  const padY = 12;
  const values = points.map((p) => p.latency_ms);
  const maxV = Math.max(...values, 1);
  // Round the top of the axis up to a clean value for readable ticks.
  const axisMax = niceCeil(maxV);

  const x = (i: number) =>
    padX + (i / Math.max(points.length - 1, 1)) * (width - padX * 2);
  const y = (v: number) =>
    height - padY - (v / axisMax) * (height - padY * 2);

  const line = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(p.latency_ms)}`)
    .join(" ");
  const area = `${line} L${x(points.length - 1)},${height - padY} L${x(0)},${
    height - padY
  } Z`;

  const hoverPoint = hover != null ? points[hover] : null;

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full"
        role="img"
        aria-label={`Response time over the last ${points.length} successful checks`}
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-accent)" stopOpacity="0.25" />
            <stop offset="100%" stopColor="var(--color-accent)" stopOpacity="0" />
          </linearGradient>
        </defs>

        {[0, 0.5, 1].map((f) => (
          <line
            key={f}
            x1={padX}
            x2={width - padX}
            y1={y(axisMax * f)}
            y2={y(axisMax * f)}
            stroke="var(--color-line-soft)"
            strokeWidth="1"
          />
        ))}

        <path d={area} fill={`url(#${gradientId})`} />
        <path
          d={line}
          fill="none"
          stroke="var(--color-accent)"
          strokeWidth="1.75"
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {hoverPoint && hover != null && (
          <>
            <line
              x1={x(hover)}
              x2={x(hover)}
              y1={padY}
              y2={height - padY}
              stroke="var(--color-ink-faint)"
              strokeWidth="1"
              strokeDasharray="2 2"
            />
            <circle
              cx={x(hover)}
              cy={y(hoverPoint.latency_ms)}
              r="3"
              fill="var(--color-accent)"
            />
          </>
        )}

        {/* Invisible hit targets for hover */}
        {points.map((p, i) => (
          <rect
            key={p.checked_at}
            x={x(i) - (width - padX * 2) / points.length / 2}
            y={0}
            width={Math.max((width - padX * 2) / points.length, 4)}
            height={height}
            fill="transparent"
            onMouseEnter={() => setHover(i)}
          />
        ))}
      </svg>

      <div className="mt-1 flex justify-between text-[11px] text-ink-faint">
        <span>{fmtDateTime(points[0].checked_at)}</span>
        <span>{axisMax} ms max</span>
        <span>{fmtDateTime(points[points.length - 1].checked_at)}</span>
      </div>

      {hoverPoint && (
        <div className="pointer-events-none absolute right-2 top-2 rounded-md border border-line bg-raised px-2 py-1 text-xs text-ink shadow-lg">
          <span className="font-mono tabular-nums">{fmtMs(hoverPoint.latency_ms)}</span>
          <span className="ml-2 text-ink-dim">{fmtDateTime(hoverPoint.checked_at)}</span>
        </div>
      )}
    </div>
  );
}

function niceCeil(v: number): number {
  const pow = 10 ** Math.floor(Math.log10(v));
  const n = v / pow;
  const nice = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
  return nice * pow;
}
