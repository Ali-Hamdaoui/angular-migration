from __future__ import annotations
import json, re, subprocess, sys
from pathlib import Path
from collections import Counter

root=Path(__file__).resolve().parents[1]
errors=[]
def fail(msg): errors.append(msg)
expected_goals=10
expected_features={*(f'S3-F{i:02d}' for i in range(1,15)),*(f'S4-F{i:02d}' for i in range(1,16))}
expected_feature_jira={*(f'AMFA-{i}' for i in range(140,154)),*(f'AMFA-{i}' for i in range(211,226))}
expected_subtasks={*(f'AMFA-{i}' for i in range(154,210)),*(f'AMFA-{i}' for i in range(226,286))}
req_shared=['ARCHITECTURE.md','UPSTREAM_SPRINT2_BOUNDARY.md','CURRENT_REPOSITORY_BASELINE.md','CURRENT_CODE_INVENTORY.json','PARALLEL_EXECUTION.md','WORKTREE_RULES.md','RUNTIME_ISOLATION.md','HERMES_RUNTIME_POLICY.md','LINUX_VM_BOOTSTRAP.md','LIVE_REPOSITORY_VERIFICATION.md','GOAL10_TWO_PHASE_PROTOCOL.md','HUMAN_SIGNOFF_POLICY.md','SUBAGENT_PROTOCOL.md','CODING_STANDARDS.md','TEST_STANDARDS.md','MANUAL_TEST_STANDARDS.md','SECURITY_STANDARDS.md','DATABASE_MIGRATION_POLICY.md','API_EVENT_CONTRACT_POLICY.md','DOCUMENTATION_STANDARDS.md','COMPLETION_CONTRACT.md','INTEGRATION_HANDOFF.md','REFERENCES.md','CONTRACT_REGISTRY.yaml','CONTRACT_REGISTRY.json','FEATURE_DEPENDENCIES.json','SHARED_FILE_REGISTRY.yaml']
for f in req_shared:
    if not (root/'shared'/f).is_file(): fail('missing shared/'+f)

goals=sorted(p for p in root.iterdir() if p.is_dir() and re.match(r'\d{2}-',p.name))
if len(goals)!=expected_goals: fail(f'expected {expected_goals} goals, got {len(goals)}')
seen_features=[]; seen_fjira=[]; seen_subtasks=[]
for g in goals:
    for f in ['GOAL.md','SOURCE_CONTRACT.md','CURRENT_CODE_MAP.md','CROSS_GOAL_CONTRACTS.md','TASK_INDEX.md','ACCEPTANCE.md','OWNERSHIP.yaml','JIRA.md','REFERENCES.md','MANUAL_TEST_PLAN.md']:
        if not (g/f).is_file(): fail(f'{g.name}: missing {f}')
    txt=(g/'GOAL.md').read_text()
    if '| Base branch | `goal` |' not in txt: fail(f'{g.name}: wrong base branch')
    if '/home/ubuntu/amfa-runtime/' not in txt: fail(f'{g.name}: external runtime absent')
    if '.runtime/' in txt: fail(f'{g.name}: repository-local runtime reference')
    if 'git push --set-upstream origin hermes/' not in txt: fail(f'{g.name}: assigned push rule absent')
    jira=(g/'JIRA.md').read_text()
    seen_features += re.findall(r'\| (S[34]-F\d{2}) \|',jira)
    seen_fjira += re.findall(r'\| S[34]-F\d{2} \| (AMFA-\d+) \|',jira)
    seen_subtasks += re.findall(r'\| S[34]-F\d{2} \| AMFA-\d+ \| S[34]-F\d{2}-I\d{2} \| (AMFA-\d+) \|',jira)
    for task in (g/'tasks').glob('T*.md'):
        tt=task.read_text()
        if 'Fixer applies approved findings.' in tt: fail(f'{task}: unconditional fixer wording')
        if 'Only when the reviewer returns `FAIL`' not in tt: fail(f'{task}: conditional fix rule absent')
    for req in ['C90-capability-contract-integration-tests.md','C91-independent-manual-runtime-validation.md','C92-as-built-documentation.md','C93-final-audits-completion-push.md']:
        if not (g/'tasks'/req).is_file(): fail(f'{g.name}: closeout task absent {req}')
    manual=list((g/'manual-tests').glob('MT-*.md'))
    if len(manual)<4: fail(f'{g.name}: insufficient manual tests')
    for p in manual:
        mt=p.read_text()
        if 'authoritative-scenario' in p.name and re.search(r'## Exact backlog manual scenario\s*\n\s*## Required evidence',mt): fail(f'{g.name}: empty manual case {p.name}')
    for req in ['current-state-gap-map.json','dependency-status.json','task-result.json','manual-test-report.json','documentation-report.json','shared-file-changes.json','database-migration.json','completion.json']:
        if not (g/'evidence-templates'/req).is_file(): fail(f'{g.name}: missing evidence {req}')

fc=Counter(seen_features); fj=Counter(seen_fjira)
if set(fc)!=expected_features or any(fc[x]!=4 for x in expected_features): fail('feature coverage must be exactly four subtask rows each')
if set(fj)!=expected_feature_jira or any(fj[x]!=4 for x in expected_feature_jira): fail('feature Jira coverage incorrect')
if set(seen_subtasks)!=expected_subtasks or len(seen_subtasks)!=116 or len(set(seen_subtasks))!=116: fail('subtask coverage/uniqueness incorrect')

expected_deps={'S3-F01': ['S2-F07'], 'S3-F02': ['S3-F01'], 'S3-F03': ['S3-F02'], 'S3-F04': ['S3-F02', 'S3-F03'], 'S3-F05': ['S2-F07', 'S3-F04'], 'S3-F06': ['S3-F05'], 'S3-F07': ['S3-F06'], 'S3-F08': ['S3-F07'], 'S3-F09': ['S3-F08'], 'S3-F10': ['S3-F09'], 'S3-F11': ['S3-F10'], 'S3-F12': ['S3-F11'], 'S3-F13': ['S3-F10', 'S3-F11', 'S3-F12'], 'S3-F14': ['S3-F13'], 'S4-F01': ['S3-F02', 'S3-F12'], 'S4-F02': ['S4-F01'], 'S4-F03': ['S4-F01', 'S4-F02'], 'S4-F04': ['S4-F03', 'S2-F03'], 'S4-F05': ['S4-F04'], 'S4-F06': ['S4-F05'], 'S4-F07': ['S4-F06'], 'S4-F08': ['S4-F07', 'S3-F13'], 'S4-F09': ['S4-F08'], 'S4-F10': ['S3-F04', 'S3-F14', 'S4-F09'], 'S4-F11': ['S2-F03', 'S4-F10'], 'S4-F12': ['S3-F14', 'S4-F08', 'S4-F10'], 'S4-F13': ['S4-F12'], 'S4-F14': ['S4-F11', 'S4-F13'], 'S4-F15': ['S4-F01', 'S4-F02', 'S4-F03', 'S2-F03', 'S4-F04', 'S4-F05', 'S4-F06', 'S4-F07', 'S4-F08', 'S4-F09', 'S4-F10', 'S4-F11', 'S4-F12', 'S4-F13', 'S4-F14']}
if json.loads((root/'shared/FEATURE_DEPENDENCIES.json').read_text())!=expected_deps: fail('dependency graph differs from backlog')

digest=json.loads((root/'SOURCE_DIGESTS.json').read_text())
if set(digest['features'])!=expected_features: fail('feature digest coverage mismatch')
if set(digest['subissues'])!={f'{f}-I{i:02d}' for f in expected_features for i in range(1,5)}: fail('subissue digest coverage mismatch')
for g in goals:
    src=(g/'SOURCE_CONTRACT.md').read_text()
    marks=dict(re.findall(r'<!-- (S[34]-F\d{2}) sha256:([0-9a-f]{64}) -->',src))
    jfeatures=set(re.findall(r'\| (S[34]-F\d{2}) \| AMFA-',(g/'JIRA.md').read_text()))
    if set(marks)!=jfeatures: fail(f'{g.name}: source markers mismatch')
    for f,h in marks.items():
        if digest['features'].get(f)!=h: fail(f'{g.name}: feature digest mismatch {f}')
    for task in (g/'tasks').glob('T*.md'):
        tt=task.read_text(); im=re.search(r'# Task \d+ — (S[34]-F\d{2}-I\d{2})',tt); hm=re.search(r'Source contract SHA-256: `([0-9a-f]{64})`',tt)
        if not im or not hm or digest['subissues'].get(im.group(1))!=hm.group(1): fail(f'{task}: subissue digest mismatch')

inv=json.loads((root/'shared/CURRENT_CODE_INVENTORY.json').read_text())
if inv.get('file_count')!=478 or len(inv.get('files',[]))!=478: fail(f'expected exact source inventory 478, got {inv.get("file_count")}')
paths={x['path'] for x in inv['files']}
if any('__pycache__' in p or '.pytest_cache' in p or p.endswith('.pyc') for p in paths): fail('inventory contains transient cache/bytecode')
if inv.get('source_zip_sha256')!='992e6ee1e66ed774a680d5e8682052707bd5a307eab4ae9b6c959e6c36263dbc': fail('source zip checksum mismatch')
for g in goals:
    cmap=(g/'CURRENT_CODE_MAP.md').read_text()
    for path in re.findall(r'`([^`]+)` — present in uploaded archive',cmap):
        if path not in paths and not any(p.startswith(path.rstrip('/')+'/') for p in paths): fail(f'{g.name}: absent code anchor {path}')

contracts=list((root/'shared/contracts').glob('*.schema.json'))
if len(contracts)<32: fail(f'expected >=32 schemas, got {len(contracts)}')
for p in contracts:
    try: d=json.loads(p.read_text())
    except Exception as e: fail(f'invalid JSON {p.name}: {e}'); continue
    if d.get('type')!='object': fail(f'{p.name}: top type not object')
reg=json.loads((root/'shared/CONTRACT_REGISTRY.json').read_text())
if reg.get('version')!='3.0.0': fail('contract registry not V3')
regfiles={c['file'] for c in reg['contracts']}
if regfiles!={f'contracts/{p.name}' for p in contracts}: fail('contract registry/files mismatch')
review=json.loads((root/'shared/contracts/repair_review_decision.schema.json').read_text())
if any('diff' in k.lower() and k!='proposal_diff_checksum' for k in review['properties']): fail('reviewer schema authoring field')

cfg=(root/'HERMES_CONFIG.example.yaml').read_text()
for token in ['agent:','max_turns: 90','goals:','max_turns: 60','backend: local','max_concurrent_children: 2']:
    if token not in cfg: fail('Hermes config missing '+token)
if 'max_iterations' in cfg: fail('unsupported delegation.max_iterations remains')

g10=root/'10-full-runtime-proof'; g10text=(g10/'GOAL.md').read_text()
for token in ['Phase A','harness_ready','Phase B','integration_verified','Never claim AMFA-225 complete']:
    if token not in g10text: fail('Goal10 missing '+token)
if '# E.' in (g10/'SOURCE_CONTRACT.md').read_text(): fail('Goal10 source contract overflow into appendices')
for p in (g10/'tasks').glob('T0[1-4]-*.md'):
    if '# E.' in p.read_text(): fail(f'Goal10 task overflow {p.name}')
completion=json.loads((root/'shared/contracts/goal_completion.schema.json').read_text())
for field in ['completion_level','harness_ready','jira_complete','blocked_integrated_criteria','human_product_signoff','goal_package_sha256']:
    if field not in completion['properties']: fail('completion schema missing '+field)

for name in ['prepare-base-branch.sh','create-worktrees.sh','check-goal-worktree.sh','check-vm-readiness.sh','prepare-goal-environment.sh','install-package.sh']:
    p=root/'scripts'/name
    if not p.is_file(): fail('missing script '+name); continue
    r=subprocess.run(['bash','-n',str(p)],capture_output=True,text=True)
    if r.returncode: fail(f'{name}: bash syntax {r.stderr}')
prep=(root/'scripts/prepare-base-branch.sh').read_text()
if 'origin/dev' in prep or 'ALLOW_CREATE_GOAL_BRANCH' in prep: fail('base script may create goal from dev')
if (root/'AUDIT_V1_FINDINGS_AND_V2_CORRECTIONS.md').exists(): fail('stale V2 audit file must not ship')
create=(root/'scripts/create-worktrees.sh').read_text()
for token in ['.base-lock.json','base drift','session.json','root_agents_sha256','not based on locked goal SHA','remote mismatch']:
    if token not in create: fail('worktree script missing '+token)

agents=Path('/mnt/data/AGENTS_AMFA_HERMES_V3.md')
if agents.exists():
    at=agents.read_text()
    if len(at)>20000: fail(f'AGENTS context too large: {len(at)}')
    for token in ['Product summary','Only when review is `FAIL`','harness_ready','local terminal backend','human product sign-off']:
        if token.lower() not in at.lower(): fail('AGENTS missing '+token)

idx=(root/'GOAL_INDEX.yaml').read_text()
for token in ['base_branch: goal','runtime_root: /home/ubuntu/amfa-runtime','execution_mode: ten_parallel_contract_first_v3']:
    if token not in idx: fail('index missing '+token)

if errors:
    print('\n'.join(errors)); sys.exit(1)
print(f'PASS V3: {len(goals)} goals, 29 features, 116 Jira subtasks, 478 source files, {len(contracts)} schemas, Goal10 two-phase semantics and scripts validated')
