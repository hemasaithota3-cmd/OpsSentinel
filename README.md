# 🚨 OpsSentinel

**OpsSentinel** is a memory-driven incident intelligence and safe-recovery copilot for engineering teams.

It does not simply read logs and suggest generic fixes. It investigates production-like incidents using evidence, remembers what the team learned from previous incidents, checks whether a historical fix is still safe to apply, and verifies whether recovery actually worked.

> **OpsSentinel helps on-call engineers investigate faster, avoid repeating failed fixes, and turn every resolved incident into reusable operational knowledge.**

---

## 🧠 The problem

When production breaks, on-call engineers do not lack data.

They lack **connected context**.

The evidence is usually scattered across:

- Alerts and metrics
- Application logs
- Distributed traces
- Deployment history
- Incident channels
- Runbooks
- Post-mortems
- Old Slack discussions
- Individual engineers’ memories

A new incident may look similar to one resolved months ago, but the engineer may not remember:

- What the actual root cause was
- Which fix worked
- Which fix failed
- Why a previously successful fix may now be unsafe
- Which service dependencies were affected
- What commitments or changes preceded the failure

Traditional observability tools show signals.

Traditional AI assistants summarize them.

**OpsSentinel connects the signals into an evolving incident reality—and learns from the outcome.**

---

## 💡 What OpsSentinel does

OpsSentinel investigates incidents through a controlled, evidence-driven workflow:

1. Detects an abnormal service condition
2. Collects relevant logs, metrics, deployment history, and dependency context
3. Forms and ranks competing root-cause hypotheses
4. Retrieves relevant lessons from previous incidents using Hindsight
5. Checks whether a historical fix applies to the current situation
6. Proposes a safe recovery action with risks and expected impact
7. Requires human approval before executing a state-changing action
8. Verifies whether the system actually recovered
9. Retains the complete incident experience for future incidents

The result is not just a diagnosis.

It is a system that becomes more useful as the team accumulates operational experience.

---

## ✨ Key capabilities

### 1. Incident Simulation Lab

OpsSentinel includes a controlled simulation environment that generates realistic incident scenarios without risking real production systems.

Supported scenarios include:

- Database connection-pool exhaustion
- API latency spikes
- Service error-rate increases
- Failed deployments
- Memory pressure
- Disk-capacity pressure
- Queue backlog
- Cascading service failures

Each scenario produces consistent telemetry, logs, service health, and recovery outcomes. The agent must investigate the available evidence rather than being told the hidden root cause.

### 2. Evidence-based investigation

OpsSentinel does not accept the first plausible explanation.

It builds an investigation timeline and evaluates multiple hypotheses using:

- Error logs
- Latency and error-rate metrics
- Resource utilization
- Recent deployment changes
- Service dependency relationships
- Historical incident memory

Every conclusion is linked to the evidence that supports it.

### 3. Hindsight-powered incident memory

Hindsight is the core learning layer of OpsSentinel.

OpsSentinel retains:

- Incident symptoms
- Logs and metrics
- Deployment context
- Engineer observations
- Root-cause findings
- Recovery actions
- Successful fixes
- Failed fixes
- Recovery preconditions
- Post-mortems
- Runbook lessons

It then recalls relevant historical incidents when a new incident occurs.

Most importantly, OpsSentinel remembers not only what worked—but **when it worked and when it should not be reused**.

### 4. Safe recovery planning

OpsSentinel separates investigation from execution.

For every proposed recovery action, it shows:

- The recommended action
- The evidence supporting it
- The expected effect
- Potential risks
- Required preconditions
- Rollback or reversal guidance
- Human approval requirement

OpsSentinel never automatically executes destructive or production-changing actions. A human engineer approves every consequential recovery step.

### 5. Recovery verification

After an approved action is applied in the simulated environment, OpsSentinel checks the actual system state.

It verifies whether:

- Error rates decreased
- Latency returned to normal
- Resource pressure reduced
- Dependent services recovered
- The original symptom disappeared

If recovery fails, OpsSentinel records that outcome and escalates the investigation rather than falsely declaring success.

### 6. Learning comparison

OpsSentinel can run the same incident scenario with and without historical memory.

This makes the value of Hindsight visible:

| Mode | Behavior |
|---|---|
| Without memory | The agent investigates from scratch and may recommend a generic or previously failed fix |
| With memory | The agent recalls relevant incidents, adapts its recommendation, and avoids known unsafe approaches |

---

## 🧩 How Hindsight is used

Hindsight is central to OpsSentinel’s intelligence loop.

| Hindsight operation | What OpsSentinel does |
|---|---|
| `retain` | Stores incident evidence, actions, outcomes, post-mortems, and operational lessons |
| `recall` | Finds similar incidents, known causes, effective fixes, failed approaches, and service patterns |
| `reflect` | Reasons over incident memory to produce a diagnosis, recovery recommendation, and risk assessment |

Hindsight extracts facts, entities, and relationships from retained content rather than storing raw transcripts. Its recall combines semantic, keyword, graph, and temporal retrieval strategies, while its reflect operation performs an agentic reasoning loop over the memory bank. [102][103]

### Memory examples

After resolving an incident, OpsSentinel retains a lesson such as:

```text
INC-101: Payment API latency increased after deployment.

Root cause: Application connection-pool exhaustion.

Effective fix: Increased application connection pool and recycled stale connections.

Precondition: Database connection usage was below capacity.

Failed approach: Restarting the service alone temporarily reduced latency,
but the issue returned.

Verification: Error rate and latency returned to normal after recovery.
```

During a later similar incident, OpsSentinel recalls this lesson.

If the current database has spare capacity, it may recommend the same class of fix.

If the database is already saturated, it warns:

```text
The previously successful connection-pool fix is not appropriate here.
Database connections are already at capacity.
Investigate recent deployment changes, long-running queries,
and downstream dependency saturation before changing pool limits.
```

This is the difference between retrieving an old answer and applying operational judgment.

---

## 🏗️ Architecture

```text
┌─────────────────────────────────────────────┐
│              Incident Command Center         │
│  Timeline · Evidence · Hypotheses · Actions  │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│             Incident Coordination Layer       │
│     Shared live state for the active incident │
└───────┬───────────────┬───────────────┬──────┘
        │               │               │
        ▼               ▼               ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│ Detection      │ │ Investigation  │ │ Recovery       │
│ Agent          │ │ Agent          │ │ Planner        │
└───────┬───────┘ └───────┬───────┘ └───────┬───────┘
        │                 │                 │
        └────────────┬────┴─────────────────┘
                     ▼
        ┌─────────────────────────┐
        │     Hindsight Memory     │
        │  Retain · Recall · Reflect│
        └─────────────────────────┘
                     │
                     ▼
        ┌─────────────────────────┐
        │   Simulation Environment │
        │  Controlled fault engine │
        └─────────────────────────┘
```

### Separation of concerns

| Layer | Responsibility |
|---|---|
| Live incident state | Tracks the current incident: symptoms, evidence, hypotheses, actions, approvals, and recovery status |
| Hindsight memory | Preserves durable operational experience across incidents |
| Simulation environment | Generates controlled faults and evaluates recovery outcomes |
| Agent workflow | Coordinates investigation, memory, planning, approval, and verification |
| Human approval | Prevents unsafe or unauthorized production changes |

Hindsight memory banks are isolated containers for memories, facts, entities, and relationships. OpsSentinel uses a dedicated memory bank for incident experience, with tags for service, severity, incident ID, environment, and outcome. [102][103]

---

## 🧪 Demo scenario

### The incident

A payment service begins returning errors during a deployment.

```text
INC-1042 — Critical
Service: Payment API
Symptom: Checkout requests fail with HTTP 500 errors.
Signal: Database connections reach 100%.
Deployment: payments-api v2.8.1 deployed 12 minutes earlier.
Affected services: Payment API, Checkout, Order Service.
```

### First investigation

OpsSentinel identifies:

- A latency increase in the Payment API
- A rise in database connection usage
- A deployment shortly before the incident
- Downstream failures in Checkout and Order Service

It proposes:

```text
Likely root cause: Application connection-pool exhaustion.

Recommended action:
Increase the application connection pool and recycle stale connections.

Risk:
Do not increase pool limits if the database is already saturated.

Approval required before execution.
```

The engineer approves the action.

OpsSentinel applies it in the simulation environment, verifies that latency and error rates recover, and retains the outcome in Hindsight.

### The learning moment

Later, a similar incident occurs.

OpsSentinel recalls INC-101 and checks the current conditions.

If the database has capacity, it recommends the proven recovery approach.

If the database is saturated, it rejects the old fix and investigates the actual bottleneck.

This demonstrates that OpsSentinel does not blindly repeat history—it applies it intelligently.

---

## 📊 What makes it different

| Traditional observability tool | Generic AI assistant | OpsSentinel |
|---|---|---|
| Shows metrics and alerts | Summarizes available context | Connects evidence into an incident narrative |
| Requires manual correlation | May give generic advice | Forms and tests competing hypotheses |
| Forgets resolution context | May repeat generic fixes | Remembers successful and failed fixes |
| Provides dashboards | Provides answers | Provides evidence, risks, approvals, and verification |
| Knowledge is scattered | Context is session-based | Builds durable organizational memory |

OpsSentinel is designed around a simple principle:

> **An incident response system should remember what the team learned—and know when that lesson no longer applies.**

---

## 🛠️ Technology stack

| Layer | Technology |
|---|---|
| Frontend | React, TypeScript, Tailwind CSS |
| Backend | Python, FastAPI |
| Agent orchestration | LangGraph |
| Long-term memory | Hindsight |
| LLM | Groq or another OpenAI-compatible model |
| Incident database | PostgreSQL or SQLite |
| Simulation | Docker Compose-based controlled environment |
| Observability simulation | Synthetic metrics, logs, traces, and deployment events |

Hindsight provides durable memory and reasoning over incident experience. The application maintains live incident state, executes approved actions, and verifies recovery in the simulation environment.

---

## 🚀 Getting started

### Prerequisites

- Python 3.11+
- Docker
- Hindsight Cloud account or local Hindsight instance
- LLM API key

### Installation

```bash
git clone [https://github.com/your-username/opsentinel.git](https://github.com/your-username/opsentinel.git)
cd opsentinel

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

### Configure environment variables

```env
HINDSIGHT_BASE_URL=[https://api.hindsight.vectorize.io](https://api.hindsight.vectorize.io)
HINDSIGHT_API_KEY=your_hindsight_api_key
HINDSIGHT_BANK_ID=opsentinel-incidents

LLM_API_KEY=your_llm_api_key
LLM_MODEL=your_selected_model
```

### Run the application

```bash
docker compose up --build
```

Or run locally:

```bash
uvicorn app.main:app --reload
```

Then open the Incident Command Center in your browser.

---

## 🎬 Demo flow

1. Open the Incident Command Center
2. Trigger a controlled payment-service incident
3. Watch OpsSentinel collect logs, metrics, and deployment context
4. Review the ranked root-cause hypotheses and supporting evidence
5. Review the recommended recovery action and its risks
6. Approve the action
7. Watch recovery verification
8. See the incident outcome retained in Hindsight
9. Trigger a similar future incident
10. Observe that OpsSentinel recalls the prior lesson and adapts its recommendation
11. Trigger a look-alike incident where the old fix is unsafe
12. Observe that OpsSentinel rejects blind reuse and investigates the actual cause

---

## 📈 Success metrics

OpsSentinel is evaluated using repeatable simulation scenarios.

| Metric | Meaning |
|---|---|
| Correct diagnosis rate | Percentage of incidents where the top hypothesis matches the hidden fault |
| Investigation efficiency | Number of investigation steps required to reach a supported diagnosis |
| Unsafe recommendation rate | Number of recommendations that violate known recovery preconditions |
| Verified recovery rate | Percentage of approved actions that produce verified recovery |
| Memory relevance | Whether recalled historical incidents are actually applicable |
| Memory benefit | Improvement in diagnosis or recovery when historical memory is available |

These are simulation-based evaluation metrics, not production reliability guarantees.

---

## 🔐 Safety principles

OpsSentinel is designed with a human-in-the-loop recovery model.

- Investigation is read-only by default
- Recovery actions require explicit human approval
- The system displays expected impact, risks, and rollback guidance
- Every action and approval is recorded in an audit trail
- Recovery success is verified using actual simulated system state
- Failed recovery triggers escalation rather than false confidence
- Sensitive values in logs are redacted before retention

AI incident-response systems should preserve human approval for high-risk infrastructure changes and production deployments. [85][87]

---

## 🗺️ Roadmap

### Phase 1: Core incident intelligence

- Incident Simulation Lab
- Evidence-based investigation
- Hindsight memory integration
- Recovery planning
- Human approval workflow
- Recovery verification
- Incident command center

### Phase 2: Reliability intelligence

- Service dependency graph
- Predictive capacity warnings
- What-if recovery analysis
- Automatic post-mortem generation
- Runbook learning
- Incident pattern detection

### Phase 3: Enterprise readiness

- Real observability integrations
- Role-based access control
- Multi-environment support
- Audit and compliance controls
- Business-impact analysis
- Executive reliability reports

---

## 🤝 Contributing

Contributions are welcome.

Please open an issue before submitting a major change. Ensure that new incident scenarios include:

- Realistic telemetry
- A clear root cause
- Evidence available to the agent
- Safe and unsafe recovery paths
- Expected verification outcomes

---

## 📄 License

MIT License

---

## 🙌 Acknowledgements

Built with [Hindsight](https://hindsight.vectorize.io/) by Vectorize.

Hindsight provides long-term, structured memory for AI agents through fact extraction, entity linking, multi-strategy retrieval, and memory-grounded reflection. [102][103]