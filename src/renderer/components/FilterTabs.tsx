import React from "react";
import type { ValuationFilter } from "../types";

interface FilterTabsProps {
  active: ValuationFilter;
  onChange: (filter: ValuationFilter) => void;
  counts: Record<ValuationFilter, number>;
}

const FILTERS: { key: ValuationFilter; label: string; dotColor: string }[] = [
  { key: "全部", label: "全部", dotColor: "#e2e8f0" },
  { key: "低估", label: "低估", dotColor: "#22c55e" },
  { key: "正常", label: "正常", dotColor: "#eab308" },
  { key: "高估", label: "高估", dotColor: "#ef4444" },
];

const FilterTabs: React.FC<FilterTabsProps> = ({ active, onChange, counts }) => {
  return (
    <div className="mx-3 mb-2 flex items-center gap-1">
      {FILTERS.map((f) => {
        const isActive = active === f.key;
        const count = counts[f.key];

        return (
          <button
            key={f.key}
            onClick={() => onChange(f.key)}
            className={`
              flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-medium
              transition-all duration-200
              ${
                isActive
                  ? "bg-slate-700/60 text-slate-200 border border-white/10"
                  : "bg-transparent text-slate-500 hover:text-slate-300 hover:bg-slate-700/30 border border-transparent"
              }
            `}
          >
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{ backgroundColor: f.dotColor }}
            />
            {f.label}
            <span className="text-[10px] text-slate-500 ml-0.5 tabular-nums">
              {count}
            </span>
          </button>
        );
      })}
    </div>
  );
};

export default FilterTabs;
