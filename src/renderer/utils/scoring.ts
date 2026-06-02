/**
 * 估值温度评分系统
 *
 * valuationScore = 100 - average(PE百分位, PB百分位)
 *   → 估值越便宜，得分越高
 *
 * profitabilityScore = average(ROE标准化, ROA标准化)
 *   → ROE [0, 30] 映射到 [0, 100]
 *   → ROA [0, 15] 映射到 [0, 100]
 *
 * riskScore = ERP标准化
 *   → ERP 越高，风险补偿越好
 *   → ERP [0, 8] 映射到 [0, 100]
 *
 * weightedScore =
 *   valuationScore * 0.5 +
 *   profitabilityScore * 0.25 +
 *   riskScore * 0.25
 *
 * temperature = 100 - weightedScore
 *   → temperature 越低 ≈ 越低估 ≈ 越值得关注
 */

export interface ScoringInput {
  pePercentile: number;
  pbPercentile: number;
  roe: number;
  roa: number;
  erp: number;
}

function normalize(value: number, min: number, max: number): number {
  const clamped = Math.max(min, Math.min(max, value));
  return ((clamped - min) / (max - min)) * 100;
}

export function computeTemperature(input: ScoringInput): number {
  const { pePercentile, pbPercentile, roe, roa, erp } = input;

  // 估值得分: PE/PB 百分位越低，得分越高
  const valuationScore = 100 - (pePercentile + pbPercentile) / 2;

  // 盈利质量得分: ROE [0, 30] → [0, 100], ROA [0, 15] → [0, 100]
  const roeScore = normalize(roe, 0, 30);
  const roaScore = normalize(roa, 0, 15);
  const profitabilityScore = (roeScore + roaScore) / 2;

  // 风险补偿得分: ERP [0, 8] → [0, 100]
  const riskScore = normalize(erp, 0, 8);

  // 加权综合得分
  const weightedScore =
    valuationScore * 0.5 +
    profitabilityScore * 0.25 +
    riskScore * 0.25;

  // 温度 = 100 - 得分
  // 温度越低 → 越低估
  const temperature = 100 - weightedScore;

  return Math.max(0, Math.min(100, temperature));
}

export function getValuationStatus(
  temperature: number
): "低估" | "正常" | "高估" {
  if (temperature < 30) return "低估";
  if (temperature <= 70) return "正常";
  return "高估";
}
