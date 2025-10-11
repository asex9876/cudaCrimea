import client from "./client";
import type { DashboardSummary } from "./types";

export const fetchDashboardSummary = async (): Promise<DashboardSummary> => {
  const { data } = await client.get<DashboardSummary>("/dashboard/summary");
  return data;
};
