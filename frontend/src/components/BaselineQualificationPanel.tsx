"use client";
import { useState } from "react";
import { decideG03, qualifyBaseline } from "@/api/baselineG03";
import type { BaselineAssessmentResponse } from "@/types/generated/api";
export function BaselineQualificationPanel({runId,stateVersion}:{runId:string;stateVersion:number}) {
 const [assessment,setAssessment]=useState<BaselineAssessmentResponse|null>(null); const [busy,setBusy]=useState(false); const [error,setError]=useState<string|null>(null);
 const act=async (fn:()=>Promise<BaselineAssessmentResponse>)=>{setBusy(true);setError(null);try{setAssessment(await fn())}catch(e){setError(e instanceof Error?e.message:"Request failed")}finally{setBusy(false)}};
 return <section aria-label="Baseline qualification"><h2>Baseline qualification / G03</h2>{assessment?<><p data-testid="qualification-status">{assessment.status}</p><p>Policy: {assessment.policy}</p><p>Evidence: {assessment.evidence_set_checksum}</p>{assessment.blockers.length>0?<ul>{assessment.blockers.map(x=><li key={x}>{x}</li>)}</ul>:<p>Evidence is ready for review.</p>}<button disabled={busy||assessment.blockers.length>0} onClick={()=>void act(()=>decideG03(runId,{expected_state_version:assessment.state_version,idempotency_key:`g03-${Date.now()}`,actor:"reviewer",decision:"approved"}))}>Approve G03</button></>:<><button disabled={busy} onClick={()=>void act(()=>qualifyBaseline(runId,{expected_state_version:stateVersion,idempotency_key:`qualify-${Date.now()}`,actor:"reviewer",policy:"strict_clean"}))}>Qualify baseline</button></>}{error?<p role="alert">{error}</p>:null}</section>
}
