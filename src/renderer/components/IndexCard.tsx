import React from "react";
import type { ETFValuationData } from "../types";

interface IndexCardProps {
  data: ETFValuationData;
}

function getStatusColors(status: "低估" | "正常" | "高估") {
  switch (status) {
    case "低估":
      return {
        text: "#22c55e",
        bg: "rgba(34,197,94,0.12)",
        border: "rgba(34,197,94,0.25)",
        bar: "#22c55e",
      };
    case "正常":
      return {
        text: "#eab308",
        bg: "rgba(234,179,8,0.12)",
        border: "rgba(234,179,8,0.25)",
        bar: "#eab308",
      };
    case "高估":
      return {
        text: "#ef4444",
        bg: "rgba(239,68,68,0.12)",
        border: "rgba(239,68,68,0.25)",
        bar: "#ef4444",
      };
  }
}

function TempBar({ value, color }: { value: number; color: string }) {
  const pct = Math.max(2, Math.min(100, value));
  return (
    <div className="w-full h-1 bg-slate-700/50 rounded-full overflow-hidden">
      <div
        className="h-full rounded-full transition-all duration-500"
        style={{
          width: `${pct}%`,
          backgroundColor: color,
          boxShadow: `0 0 4px ${color}40`,
        }}
      />
    </div>
  );
}

const IndexCard: React.FC<IndexCardProps> = ({ data }) => {
  const colors = getStatusColors(data.valuationStatus);

  return (
    <div
      className="mx-3 mb-1.5 px-3 py-2.5 rounded-xl
                 border backdrop-blur-sm
                 transition-all duration-200
                 hover:brightness-125 hover:border-opacity-40
                 cursor-default"
      style={{
        backgroundColor: "rgba(30, 41, 59, 0.45)",
        borderColor: colors.border,
      }}
    >
      {/* Row 1: Code + Name + Status Badge */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs font-mono font-bold text-cyan-400 shrink-0">
            {data.code}
          </span>
          <span className="text-xs text-slate-300 truncate">
            {data.name}
          </span>
          <span className="text-[10px] text-slate-600 font-mono uppercase shrink-0">
            {data.market}
          </span>
        </div>
        <span
          className="text-[10px] font-semibold px-1.5 py-0.5 rounded-md shrink-0 ml-2"
          style={{
            color: colors.text,
            backgroundColor: colors.bg,
            border: `1px solid ${colors.border}`,
          }}
        >
          {data.valuationStatus}
        </span>
      </div>

      {/* Row 2: Temperature bar */}
      <div className="flex items-center gap-2 mb-2">
        <span className="text-[10px] text-slate-500 w-8 shrink-0">温度</span>
        <TempBar value={data.temperature} color={colors.bar} />
        <span
          className="text-[11px] font-mono font-bold w-10 text-right shrink-0 tabular-nums"
          style={{ color: colors.text }}
        >
          {data.temperature}°
        </span>
      </div>

      {/* Row 3: Metrics grid */}
      <div className="grid grid-cols-4 gap-1 text-center">
        <div>
          <div className="text-[9px] text-slate-500">PE分位</div>
          <div className="text-[11px] font-mono text-slate-300 tabular-nums">
            {data.pePercentile}%
          </div>
        </div>
        <div>
          <div className="text-[9px] text-slate-500">PB分位</div>
          <div className="text-[11px] font-mono text-slate-300 tabular-nums">
            {data.pbPercentile}%
          </div>
        </div>
        <div>
          <div className="text-[9px] text-slate-500">ROE</div>
          <div className="text-[11px] font-mono text-slate-300 tabular-nums">
            {data.roe}%
          </div>
        </div>
        <div>
          <div className="text-[9px] text-slate-500">ERP</div>
          <div className="text-[11px] font-mono text-slate-300 tabular-nums">
            {data.erp}%
          </div>
        </div>
      </div>
    </div>
  );
};

export default IndexCard;
