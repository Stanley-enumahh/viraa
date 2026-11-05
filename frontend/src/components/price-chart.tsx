"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

import { formatCompact, formatUsd } from "@/lib/format";
import type { HistoryRange, PriceHistory } from "@/lib/types";

const HEIGHT = 280;
const MARGIN = { top: 12, right: 12, bottom: 28, left: 56 };

function niceTicks(min: number, max: number, count = 4) {
  const rough = (max - min || Math.abs(max) || 1) / count;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((n) => n * magnitude).find((n) => n >= rough) ?? rough;
  const ticks: number[] = [];
  for (let value = Math.ceil(min / step) * step; value <= max + step * 1e-6; value += step) {
    ticks.push(Number(value.toPrecision(12)));
  }
  return ticks;
}

function formatTime(iso: string, range: HistoryRange) {
  const options: Intl.DateTimeFormatOptions =
    range === "1h" || range === "24h" ? { hour: "numeric", minute: "2-digit" } : { month: "short", day: "numeric" };
  return new Intl.DateTimeFormat(undefined, options).format(new Date(iso));
}

function formatFullTime(iso: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(iso));
}

export function PriceChart({ history, name, stale }: { history: PriceHistory; name: string; stale: boolean }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const chart = useMemo(() => {
    if (width === 0 || history.points.length < 2) return null;
    const values = history.points.map((point) => Number(point.price_usd));
    const low = Math.min(...values);
    const high = Math.max(...values);
    const padding = (high - low || high || 1) * 0.08;
    const yMin = low - padding;
    const yMax = high + padding;

    const plotWidth = width - MARGIN.left - MARGIN.right;
    const plotBottom = HEIGHT - MARGIN.bottom;
    const lastIndex = values.length - 1;
    const x = (index: number) => MARGIN.left + (index / lastIndex) * plotWidth;
    const y = (value: number) => MARGIN.top + ((yMax - value) / (yMax - yMin)) * (plotBottom - MARGIN.top);

    const line = values.map((value, index) => `${index ? "L" : "M"}${x(index).toFixed(1)} ${y(value).toFixed(1)}`).join("");
    const area = `${line}L${x(lastIndex).toFixed(1)} ${plotBottom}L${x(0).toFixed(1)} ${plotBottom}Z`;

    const labelCount = width < 480 ? 3 : 5;
    const xLabels = Array.from({ length: labelCount }, (_, i) => Math.round((i / (labelCount - 1)) * lastIndex));

    return { values, x, y, line, area, plotBottom, plotWidth, lastIndex, ticks: niceTicks(yMin, yMax), xLabels };
  }, [history, width]);

  function handlePointer(event: PointerEvent<SVGSVGElement>) {
    if (!chart) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const ratio = (event.clientX - bounds.left - MARGIN.left) / chart.plotWidth;
    setActiveIndex(Math.max(0, Math.min(chart.lastIndex, Math.round(ratio * chart.lastIndex))));
  }

  function handleKey(event: KeyboardEvent<HTMLDivElement>) {
    if (!chart) return;
    if (event.key === "Escape") {
      setActiveIndex(null);
    } else if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      const delta = event.key === "ArrowLeft" ? -1 : 1;
      setActiveIndex((current) => Math.max(0, Math.min(chart.lastIndex, (current ?? chart.lastIndex) + delta)));
    }
  }

  // Data can shrink when the range changes while a point is selected.
  const index = chart && activeIndex !== null ? Math.min(activeIndex, chart.lastIndex) : null;
  const activePoint = index !== null ? history.points[index] : null;
  const tooltipLeft = chart && index !== null ? chart.x(index) : 0;
  const flipTooltip = tooltipLeft > width * 0.6;
  const current = history.points.at(-1)?.price_usd ?? "0";

  return (
    <div
      ref={containerRef}
      tabIndex={0}
      role="group"
      aria-label={`${name} price chart. Low ${formatUsd(history.low_usd)}, high ${formatUsd(history.high_usd)}, now ${formatUsd(current)}. Use the left and right arrow keys to explore.`}
      onKeyDown={handleKey}
      onBlur={() => setActiveIndex(null)}
      className={`relative rounded-lg transition-opacity motion-reduce:transition-none ${stale ? "opacity-50" : ""}`}
      style={{ height: HEIGHT }}
    >
      {chart && (
        <svg
          width={width}
          height={HEIGHT}
          aria-hidden="true"
          className="touch-pan-y"
          onPointerMove={handlePointer}
          onPointerDown={handlePointer}
          onPointerLeave={() => setActiveIndex(null)}
        >
          {chart.ticks.map((tick) => (
            <g key={tick}>
              <line x1={MARGIN.left} x2={width - MARGIN.right} y1={chart.y(tick)} y2={chart.y(tick)} stroke="var(--line)" />
              <text
                x={MARGIN.left - 8}
                y={chart.y(tick)}
                dy="0.32em"
                textAnchor="end"
                fontSize="12"
                fill="var(--ink-3)"
                style={{ fontVariantNumeric: "tabular-nums" }}
              >
                {formatCompact(tick)}
              </text>
            </g>
          ))}
          {chart.xLabels.map((labelIndex, position) => (
            <text
              key={labelIndex}
              x={chart.x(labelIndex)}
              y={HEIGHT - 8}
              textAnchor={position === 0 ? "start" : position === chart.xLabels.length - 1 ? "end" : "middle"}
              fontSize="12"
              fill="var(--ink-3)"
            >
              {formatTime(history.points[labelIndex].t, history.range)}
            </text>
          ))}
          <path d={chart.area} fill="var(--accent)" opacity="0.1" />
          <path d={chart.line} fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          {index === null ? (
            <circle
              cx={chart.x(chart.lastIndex)}
              cy={chart.y(chart.values[chart.lastIndex])}
              r="4"
              fill="var(--accent)"
              stroke="var(--surface)"
              strokeWidth="2"
            />
          ) : (
            <>
              <line x1={chart.x(index)} x2={chart.x(index)} y1={MARGIN.top} y2={chart.plotBottom} stroke="var(--ink-3)" />
              <circle
                cx={chart.x(index)}
                cy={chart.y(chart.values[index])}
                r="4"
                fill="var(--accent)"
                stroke="var(--surface)"
                strokeWidth="2"
              />
            </>
          )}
        </svg>
      )}
      {activePoint && (
        <div
          aria-live="polite"
          className="pointer-events-none absolute top-2 rounded-lg border border-line bg-surface-raised px-3 py-2 shadow-lg"
          style={flipTooltip ? { right: width - tooltipLeft + 10 } : { left: tooltipLeft + 10 }}
        >
          <p className="font-semibold whitespace-nowrap">{formatUsd(activePoint.price_usd)}</p>
          <p className="text-xs whitespace-nowrap text-ink-2">{formatFullTime(activePoint.t)}</p>
        </div>
      )}
    </div>
  );
}

export function PriceTable({ history }: { history: PriceHistory }) {
  return (
    <details className="mt-3 text-sm">
      <summary className="cursor-pointer text-ink-2">View as a table</summary>
      <div className="mt-2 max-h-64 overflow-y-auto" tabIndex={0}>
        <table className="w-full">
          <thead className="sticky top-0 bg-surface text-left text-ink-3">
            <tr>
              <th scope="col" className="py-1.5 font-medium">Time</th>
              <th scope="col" className="py-1.5 text-right font-medium">Price (USD)</th>
            </tr>
          </thead>
          <tbody>
            {[...history.points].reverse().map((point) => (
              <tr key={point.t} className="border-t border-line">
                <td className="py-1.5 text-ink-2">{formatFullTime(point.t)}</td>
                <td className="py-1.5 text-right tabular-nums">{formatUsd(point.price_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
