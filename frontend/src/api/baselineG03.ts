import { apiClient, type createApiClient } from "./client";
import type { BaselineAssessmentResponse, BaselineQualifyRequest, G03DecisionRequest } from "@/types/generated/api";
type Client=ReturnType<typeof createApiClient>;
const path=(id:string)=>`/api/v1/runs/${encodeURIComponent(id)}`;
export const getBaselineSummary=(id:string,c:Client=apiClient)=>c.get<BaselineAssessmentResponse>(`${path(id)}/baseline/summary`);
export const qualifyBaseline=(id:string,r:BaselineQualifyRequest,c:Client=apiClient)=>c.post<BaselineAssessmentResponse>(`${path(id)}/baseline/qualify`,r);
export const decideG03=(id:string,r:G03DecisionRequest,c:Client=apiClient)=>c.post<BaselineAssessmentResponse>(`${path(id)}/approvals/G03/decisions`,r);
