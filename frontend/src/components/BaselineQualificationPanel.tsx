"use client";
import { useEffect, useState } from "react";
import { ApiClientError } from "@/api/client";
import { decideG03, getBaselineSummary, qualifyBaseline } from "@/api/baselineG03";
import { getBaselineValidation } from "@/api/baselineMatrix";
import { captureBaselineParity } from "@/api/baselineParity";
import { applyBaselineRepair } from "@/api/baselineRepair";
import { getAuthoritativeRunState } from "@/api/runs";
import type { BaselineValidationResponse } from "@/types/baselineMatrix";
import { BASELINE_TEST_RECIPE_ID } from "@/types/baselineRepair";
import type { BaselineAssessmentResponse } from "@/types/generated/api";
import { headingTag, type PanelHeadingLevel } from "./control-tower/semanticHeading";
import type { AuthoritativePackageLoad } from "./control-tower/authoritativePackageLoad";

const BASELINE_REQUIRED_TEST_NOT_PROVEN = "BASELINE_REQUIRED_TEST_NOT_PROVEN";
const REPAIR_AUTHORIZATION_COMMENT = `Operator-authorized governed baseline repair recipe ${BASELINE_TEST_RECIPE_ID} from the Control Tower.`;
const RECOVERY_ACTOR = "control-tower";
const VALIDATION_KINDS = ["build", "test", "lint"] as const;

function operationKey(runId: string, prefix: string) { return `${prefix}-${runId}-${Date.now()}`; }

function newestAssessment(a: BaselineAssessmentResponse | null, b: BaselineAssessmentResponse | null): BaselineAssessmentResponse | null {
  if (!a) return b;
  if (!b) return a;
  return a.state_version >= b.state_version ? a : b;
}

function meaningfulTestEvidence(validation: BaselineValidationResponse | undefined): boolean {
  return validation?.status === "passed" && validation.results.reduce((total, result) => total + (result.test_count ?? 0), 0) > 0;
}

export function BaselineQualificationPanel({runId,stateVersion,workflowEvents=[],refreshAuthoritativeState,authoritativeAssessment,headingLevel=2}:{runId:string;stateVersion:number;workflowEvents?:Array<{event_type:string;sequence?:number}>;refreshAuthoritativeState?:()=>Promise<void>;authoritativeAssessment?:AuthoritativePackageLoad<BaselineAssessmentResponse>;headingLevel?:PanelHeadingLevel}) {
 const Heading=headingTag(headingLevel);
 const externallyLoaded=authoritativeAssessment!==undefined;
 const [localAssessment,setAssessment]=useState<BaselineAssessmentResponse|null>(null);
 const [recoveryAssessment,setRecoveryAssessment]=useState<BaselineAssessmentResponse|null>(null);
 const [busy,setBusy]=useState(false); const [error,setError]=useState<string|null>(null);
 const [recoveryBusy,setRecoveryBusy]=useState<"repair"|"accept"|null>(null);
 const [recoveryError,setRecoveryError]=useState<string|null>(null);
 const [recoveryNotice,setRecoveryNotice]=useState<string|null>(null);
 const [validationEvidence,setValidationEvidence]=useState<Partial<Record<(typeof VALIDATION_KINDS)[number],BaselineValidationResponse>>>({});
 const qualificationRecorded=workflowEvents.some((event)=>["BASELINE_BLOCKED","BASELINE_QUALIFIED","G03_CREATED","G03_APPROVED","G03_REJECTED"].includes(event.event_type));
 const canQualify=workflowEvents.some((event)=>event.event_type==="G02_APPROVED") && workflowEvents.some((event)=>event.event_type==="BASELINE_INSTALL_SUCCEEDED");
 useEffect(()=>{if(externallyLoaded||!qualificationRecorded)return; void getBaselineSummary(runId).then(setAssessment).catch((reason: unknown)=>{if(!(reason instanceof ApiClientError && reason.status===404))setError("Baseline qualification state could not be loaded.")})},[externallyLoaded,runId,stateVersion,workflowEvents.length,qualificationRecorded]);
 const baselineContext=externallyLoaded||qualificationRecorded||canQualify;
 useEffect(()=>{
   if(!baselineContext)return;
   let active=true;
   void Promise.all(VALIDATION_KINDS.map((kind)=>getBaselineValidation(runId,kind).catch((reason: unknown)=>reason instanceof ApiClientError&&reason.status===404?null:Promise.reject(reason)))).then(([build,test,lint])=>{if(!active)return;setValidationEvidence({build:build??undefined,test:test??undefined,lint:lint??undefined})}).catch(()=>{if(active)setValidationEvidence({})});
   return ()=>{active=false};
 },[baselineContext,runId,stateVersion]);
 const externalAssessment=externallyLoaded?(authoritativeAssessment.status==="ready"?authoritativeAssessment.value:null):null;
 const assessment=newestAssessment(newestAssessment(recoveryAssessment,localAssessment),externalAssessment);
 const externalPending=externallyLoaded&&authoritativeAssessment.status!=="ready";
 const meaningfulTest=meaningfulTestEvidence(validationEvidence.test);
 const lintFailed=validationEvidence.lint?.status==="failed";
 const buildFailed=validationEvidence.build?.status==="failed";
 const repairCompletedSequence=workflowEvents.reduce((latest,event)=>event.event_type==="REPAIR_APPLY_COMPLETED"&&(event.sequence??0)>latest?event.sequence??0:latest,0);
 const freshValidationEvidence=repairCompletedSequence===0||(validationEvidence.test?.event_sequence??0)>repairCompletedSequence;
 const qualifiedClean=assessment!==null&&assessment.blockers.length===0&&(assessment.status==="qualified"||assessment.status==="qualified_with_known_failures");
 const repairAvailable=assessment!==null&&assessment.status!=="stale"&&assessment.blockers.includes(BASELINE_REQUIRED_TEST_NOT_PROVEN);
 const acceptAvailable=meaningfulTest&&freshValidationEvidence&&lintFailed&&!buildFailed&&!qualifiedClean&&assessment?.g03_decision!=="approved";
 const act=async (fn:()=>Promise<BaselineAssessmentResponse>)=>{setBusy(true);setError(null);try{setAssessment(await fn()); await refreshAuthoritativeState?.()}catch(e){setError(e instanceof Error?e.message:"Request failed")}finally{setBusy(false)}};
 const repairBaselineTest=async ()=>{
   setRecoveryBusy("repair");setRecoveryError(null);setRecoveryNotice(null);
   try{
     const [runState,freshAssessment]=await Promise.all([getAuthoritativeRunState(runId),getBaselineSummary(runId)]);
     if(!freshAssessment.blockers.includes(BASELINE_REQUIRED_TEST_NOT_PROVEN)){
       await refreshAuthoritativeState?.();
       setRecoveryError("The baseline test-evidence blocker is no longer present; refresh the authoritative state before retrying.");
       return;
     }
     await decideG03(runId,{expected_state_version:runState.state_version,idempotency_key:operationKey(runId,"g03-repair"),actor:RECOVERY_ACTOR,decision:"modification_requested",comment:REPAIR_AUTHORIZATION_COMMENT});
     const afterDecision=await getAuthoritativeRunState(runId);
     const repair=await applyBaselineRepair(runId,{expected_state_version:afterDecision.state_version,idempotency_key:operationKey(runId,"baseline-repair"),actor:RECOVERY_ACTOR,recipe_id:BASELINE_TEST_RECIPE_ID,g03_package_checksum:freshAssessment.package_checksum});
     const postRepairAssessment=await getBaselineSummary(runId).catch(()=>null);
     if(postRepairAssessment)setRecoveryAssessment(postRepairAssessment);
     setRecoveryNotice(`${repair.recipe_id} was applied by the backend. Fresh baseline test and lint validation is now required; previous validation evidence is no longer authoritative.`);
     await refreshAuthoritativeState?.();
   }catch(reason:unknown){
     setRecoveryError(reason instanceof Error?reason.message:"The governed baseline repair could not be applied.");
     await refreshAuthoritativeState?.();
   }finally{setRecoveryBusy(null);}
 };
 const acceptKnownBaselineFailures=async ()=>{
   setRecoveryBusy("accept");setRecoveryError(null);setRecoveryNotice(null);
   try{
     const beforeCapture=await getAuthoritativeRunState(runId);
     const parity=await captureBaselineParity(runId,{expected_state_version:beforeCapture.state_version,idempotency_key:operationKey(runId,"accept-defects"),actor:RECOVERY_ACTOR});
     if(parity.failures.some((failure)=>failure.kind==="test")){
       setRecoveryError("Baseline parity still contains a test failure; documented baseline defects were not accepted.");
       await refreshAuthoritativeState?.();
       return;
     }
     const afterCapture=await getAuthoritativeRunState(runId);
     const qualified=await qualifyBaseline(runId,{expected_state_version:afterCapture.state_version,idempotency_key:operationKey(runId,"qualify-known"),actor:RECOVERY_ACTOR,policy:"qualified_known_failures",company_policy_allows_known_failures:true});
     setRecoveryAssessment(qualified);
     setRecoveryNotice(`Baseline qualification completed under qualified_known_failures: ${qualified.status}.`);
     await refreshAuthoritativeState?.();
   }catch(reason:unknown){
     setRecoveryError(reason instanceof Error?reason.message:"Documented baseline defects could not be accepted.");
     await refreshAuthoritativeState?.();
   }finally{setRecoveryBusy(null);}
 };
 return <section aria-label="Baseline qualification"><Heading>Baseline qualification / G03</Heading>{externallyLoaded&&authoritativeAssessment.status==="loading"?<p>Loading baseline qualification package</p>:null}{externallyLoaded&&authoritativeAssessment.status==="unavailable"?<div><p role="status">Baseline qualification package is unavailable because the response was invalid.</p><button type="button" onClick={authoritativeAssessment.retry}>Retry baseline qualification</button></div>:null}{externallyLoaded&&authoritativeAssessment.status==="error"?<div><p role="alert">Baseline qualification package could not be loaded.</p><button type="button" onClick={authoritativeAssessment.retry}>Retry baseline qualification</button></div>:null}{!externalPending&&assessment?<><p data-testid="qualification-status">{assessment.status}</p><p>Policy: {assessment.policy}</p><p>Evidence: {assessment.evidence_set_checksum}</p>{assessment.blockers.length>0?<ul>{assessment.blockers.map(x=><li key={x}>{x}</li>)}</ul>:<p>Evidence is ready for review.</p>}{assessment.status==="stale"?<p role="status">The G03 package is stale{assessment.stale_reason?`: ${assessment.stale_reason}`:""}. Fresh baseline validation is required before continuing.</p>:null}{recoveryNotice?<p role="status">{recoveryNotice}</p>:null}{recoveryError?<p role="alert">{recoveryError}</p>:null}{repairAvailable?<div><p role="note">No meaningful baseline test was proven for this package. The approved governed recovery is the {BASELINE_TEST_RECIPE_ID} baseline repair, applied only through backend authority with an explicit G03 request-changes decision.</p><button type="button" disabled={busy||recoveryBusy!==null} onClick={()=>void repairBaselineTest()}>{recoveryBusy==="repair"?"Repairing baseline test...":"Repair baseline test"}</button></div>:null}{acceptAvailable?<div><p role="note">Meaningful baseline tests are proven and the remaining baseline validation failures are known pre-existing defects eligible for the qualified_known_failures policy.</p><button type="button" disabled={busy||recoveryBusy!==null} onClick={()=>void acceptKnownBaselineFailures()}>{recoveryBusy==="accept"?"Accepting documented baseline defects...":"Accept documented baseline defects"}</button></div>:null}{assessment.g03_decision?<p role="status">G03 decision: {assessment.g03_decision}</p>:<button disabled={busy||recoveryBusy!==null||assessment.blockers.length>0} onClick={()=>void act(()=>decideG03(runId,{expected_state_version:assessment.state_version,idempotency_key:`g03-${Date.now()}`,actor:"reviewer",decision:"approved"}))}>Approve G03</button>}</>:!externalPending&&canQualify?<><button disabled={busy||recoveryBusy!==null} onClick={()=>void act(()=>qualifyBaseline(runId,{expected_state_version:stateVersion,idempotency_key:`qualify-${Date.now()}`,actor:"reviewer",policy:"strict_clean"}))}>Qualify baseline</button>{acceptAvailable?<div><p role="note">Meaningful baseline tests are proven and the remaining baseline validation failures are known pre-existing defects eligible for the qualified_known_failures policy.</p><button type="button" disabled={busy||recoveryBusy!==null} onClick={()=>void acceptKnownBaselineFailures()}>{recoveryBusy==="accept"?"Accepting documented baseline defects...":"Accept documented baseline defects"}</button></div>:null}</>:!externalPending?<p>G03 remains hidden until G02 approval and baseline evidence are complete.</p>:null}{error?<p role="alert">{error}</p>:null}</section>
}
