import React from "react";
import type { MarketSummary } from "../types";

interface SummaryBarProps {
  summary: MarketSummary;
}

interface SummaryItemProps {
  label: string;
  value: string;
  sub?: string;
  color?: string;
}

const SummaryItem: React.FC<SummaryItemProps> = ({
  label,
  value,
  sub,
  color,
}) => (
  <div className="flex flex-col items-center min-w-0">
    <span className="text-[10px] text-slate-500 font-medium tracking-wide uppercase">
      {label}
    </span>
    <span
      className="text-sm font-bold font-mono tabular-nums"
      style={{ color: color || "#e2e8f0" }}
    >
      {value}
    </span>
    {sub && (
      <span className="text-[9px] text-slate-600 font-mono truncate max-w-full">
        {sub}
      </span>
    )}
  </div>
);

function getTemperatureColor(temp: number): string {
  if (temp < 30) return "#22c55e";
  if (temp <= 50) return "#4ade80";
  if (temp <= 70) return "#eab308";
  return "#ef4444";
}

const SummaryBar: React.FC<SummaryBarProps> = ({ summary }) => {
  const tempColor = getTemperatureColor(summary.totalTemperature);

  return (
    <div
      className="mx-3 mb-2 px-3 py-2.5 rounded-xl
                 flex items-center justify-between gap-1
                 border border-white/5
                 bg-slate-800/30 backdrop-blur-sm"
    >
      <SummaryItem
        label="全市场温度"
        value={`${summary.totalTemperature}°`}
        color={tempColor}
      />
      <div className="w-px h-8 bg-slate-600/30" />
      <SummaryItem
        label="风险溢价"
        value={`${summary.erp}%`}
        sub="ERP"
      />
      <div className="w-px h-8 bg-slate-600/30" />
      <SummaryItem
        label="10Y国债"
        value={`${summary.bond10Y}%`}
      />
      <div className="w-px h-8 bg-slate-600/30" />
      <SummaryItem
        label="低估指数"
        value={`${summary.undervaluedCount}`}
        sub={`/ ${summary.totalCount}`}
        color={summary.undervaluedCount > 0 ? "#22c55e" : undefined}
      />
    </div>
  );
};

export default SummaryBar;
