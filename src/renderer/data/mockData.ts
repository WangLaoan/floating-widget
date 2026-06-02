import type { ETFBaseInfo, ETFValuationData, MarketSummary } from "../types";
import { computeTemperature, getValuationStatus } from "../utils/scoring";

// 核心 ETF 映射表 —— 未来可直接替换为真实数据源
export const ETF_MAP: Record<string, ETFBaseInfo> = {
  "513630": { name: "港股红利低波", market: "sh" },
  "515180": { name: "A股中证红利", market: "sh" },
  "513500": { name: "标普500",     market: "sh" },
  "510880": { name: "上证红利",     market: "sh" },
  "159905": { name: "深证红利",     market: "sz" },
  "512890": { name: "中证红利低波", market: "sh" },
  "513690": { name: "恒生高股息",   market: "sh" },
  "510050": { name: "上证50",       market: "sh" },
  "510300": { name: "沪深300",      market: "sh" },
  "159915": { name: "创业板指",     market: "sz" },
  "512100": { name: "中证1000",     market: "sh" },
  "513390": { name: "纳斯达克100",  market: "sh" },
  "511260": { name: "10年国债",     market: "sh" },
  "513060": { name: "港股通央企红利", market: "sh" },
};

// Seeded pseudo-random number generator for reproducible mock data
function createRNG(seed: number) {
  let s = seed;
  return function () {
    s = (s * 16807 + 0) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function generateSingleValuation(
  code: string,
  baseInfo: ETFBaseInfo,
  rng: () => number
): ETFValuationData {
  // PE 百分位: 不同类型的指数有不同的合理范围
  const isBroad = ["513500", "510050", "510300", "159915", "512100", "513390"].includes(code);
  const isBond = code === "511260";
  const isDividend = !isBroad && !isBond;

  let pePercentile: number;
  let pbPercentile: number;
  let roe: number;
  let roa: number;

  if (isBond) {
    pePercentile = clamp(30 + rng() * 30, 20, 80);
    pbPercentile = clamp(30 + rng() * 30, 20, 80);
    roe = clamp(2.5 + rng() * 2, 2.0, 5.0);
    roa = clamp(1.0 + rng() * 1.5, 0.5, 3.0);
  } else if (isBroad) {
    pePercentile = clamp(30 + rng() * 50, 10, 95);
    pbPercentile = clamp(30 + rng() * 50, 10, 95);
    roe = clamp(8 + rng() * 12, 6, 25);
    roa = clamp(3 + rng() * 10, 2, 15);
  } else {
    // 红利类: 通常估值偏低，ROE适中
    pePercentile = clamp(10 + rng() * 45, 5, 75);
    pbPercentile = clamp(5 + rng() * 40, 3, 70);
    roe = clamp(8 + rng() * 10, 6, 18);
    roa = clamp(3 + rng() * 6, 2, 10);
  }

  // ERP: 权益风险溢价 — 红利类通常偏高，宽基居中，债券低
  let erp: number;
  if (isBond) {
    erp = clamp(0.5 + rng() * 1.0, 0.2, 1.5);
  } else if (isDividend) {
    erp = clamp(4.0 + rng() * 3.5, 3.0, 8.0);
  } else {
    erp = clamp(2.0 + rng() * 4.0, 1.5, 7.0);
  }

  const temperature = computeTemperature({
    pePercentile,
    pbPercentile,
    roe,
    roa,
    erp,
  });

  const valuationStatus = getValuationStatus(temperature);

  return {
    code,
    name: baseInfo.name,
    market: baseInfo.market,
    pePercentile: Math.round(pePercentile * 10) / 10,
    pbPercentile: Math.round(pbPercentile * 10) / 10,
    roe: Math.round(roe * 10) / 10,
    roa: Math.round(roa * 10) / 10,
    erp: Math.round(erp * 100) / 100,
    temperature: Math.round(temperature * 10) / 10,
    valuationStatus,
  };
}

export function generateMockData(): {
  data: ETFValuationData[];
  summary: MarketSummary;
} {
  // Use timestamp as seed for variety on each refresh
  const seed = Date.now() % 2147483647;
  const rng = createRNG(seed);

  const data = Object.entries(ETF_MAP).map(([code, baseInfo]) =>
    generateSingleValuation(code, baseInfo, rng)
  );

  // Sort by temperature ascending (coldest first)
  data.sort((a, b) => a.temperature - b.temperature);

  const totalTemp =
    data.reduce((sum, d) => sum + d.temperature, 0) / data.length;
  const avgERP =
    data.reduce((sum, d) => sum + d.erp, 0) / data.length;
  const undervaluedCount = data.filter(
    (d) => d.valuationStatus === "低估"
  ).length;

  const now = new Date();
  const timeStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")} ${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}`;

  const summary: MarketSummary = {
    totalTemperature: Math.round(totalTemp * 10) / 10,
    erp: Math.round(avgERP * 100) / 100,
    bond10Y: Math.round((2.5 + rng() * 1.5) * 100) / 100,
    undervaluedCount,
    totalCount: data.length,
    updateTime: timeStr,
  };

  return { data, summary };
}
