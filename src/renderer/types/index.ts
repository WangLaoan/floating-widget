export interface ETFBaseInfo {
  code: string;
  name: string;
  market: "sh" | "sz";
}

export interface ETFValuationData {
  code: string;
  name: string;
  market: "sh" | "sz";
  pePercentile: number;   // 0-100
  pbPercentile: number;   // 0-100
  roe: number;            // e.g. 12.5 meaning 12.5%
  roa: number;            // e.g. 6.2 meaning 6.2%
  erp: number;            // equity risk premium
  temperature: number;    // 0-100
  valuationStatus: "低估" | "正常" | "高估";
}

export interface MarketSummary {
  totalTemperature: number;
  erp: number;
  bond10Y: number;
  undervaluedCount: number;
  totalCount: number;
  updateTime: string;
}

export type ValuationFilter = "低估" | "正常" | "高估" | "全部";

export interface ElectronAPI {
  hideWindow: () => Promise<void>;
  minimizeWindow: () => Promise<void>;
  closeWindow: () => Promise<void>;
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI;
  }
}
