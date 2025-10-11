import client from "./client";
import type { UGCListResponse, UGCItem } from "./types";

export const fetchUGCList = async (params: { limit?: number; offset?: number } = {}): Promise<UGCListResponse> => {
  const { data } = await client.get<UGCListResponse>("/ugc", { params });
  return data;
};

export const fetchUGCItem = async (id: string): Promise<UGCItem> => {
  const { data } = await client.get<UGCItem>(`/ugc/${id}`);
  return data;
};
