import React, { useState, useCallback, useMemo } from "react";
import TopBar from "./TopBar";
import SummaryBar from "./SummaryBar";
import FilterTabs from "./FilterTabs";
import IndexCard from "./IndexCard";
import type { ETFValuationData, MarketSummary, ValuationFilter } from "../types";
import { generateMockData } from "../data/mockData";

const FloatingWidget: React.FC = () => {
  const [mockResult, setMockResult] = useState(() => generateMockData());

  const handleRefresh = useCallback(() => {
    setMockResult(generateMockData());
  }, []);

  const [filter, setFilter] = useState<ValuationFilter>("全部");

  const filteredData = useMemo(() => {
    const { data } = mockResult;
    if (filter === "全部") return data.slice(0, 8);
    return data
      .filter((d) => d.valuationStatus === filter)
      .slice(0, 8);
  }, [mockResult, filter]);

  const filterCounts = useMemo(() => {
    const { data } = mockResult;
    return {
      "全部": data.length,
      "低估": data.filter((d) => d.valuationStatus === "低估").length,
      "正常": data.filter((d) => d.valuationStatus === "正常").length,
      "高估": data.filter((d) => d.valuationStatus === "高估").length,
    };
  }, [mockResult]);

  return (
    <div
      className="w-full h-full flex flex-col overflow-hidden select-none"
      style={{
        backgroundColor: "rgba(15, 23, 42, 0.72)",
        backdropFilter: "blur(24px) saturate(1.2)",
        WebkitBackdropFilter: "blur(24px) saturate(1.2)",
        borderRadius: "16px",
        boxShadow:
          "0 8px 32px rgba(0, 0, 0, 0.45), 0 0 0 1px rgba(255, 255, 255, 0.06) inset",
      }}
    >
      {/* Top bar — draggable region */}
      <TopBar
        updateTime={mockResult.summary.updateTime}
        onRefresh={handleRefresh}
      />

      {/* Divider */}
      <div className="mx-3 h-px bg-gradient-to-r from-transparent via-slate-600/40 to-transparent" />

      {/* Summary */}
      <div className="mt-2">
        <SummaryBar summary={mockResult.summary} />
      </div>

      {/* Filters */}
      <FilterTabs
        active={filter}
        onChange={setFilter}
        counts={filterCounts}
      />

      {/* Index card list */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden custom-scrollbar pb-2">
        {filteredData.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-slate-600 text-xs">
            暂无数据
          </div>
        ) : (
          filteredData.map((item) => (
            <IndexCard key={item.code} data={item} />
          ))
        )}
      </div>

      {/* Bottom subtle branding */}
      <div className="px-3 py-1.5 text-center">
        <span className="text-[9px] text-slate-700 tracking-widest">
          估值温度 · 投资研究
        </span>
      </div>
    </div>
  );
};

export default FloatingWidget;
