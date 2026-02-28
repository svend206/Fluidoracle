# Component Performance Verification Protocol (CPVP)

**Version:** 1.0 (Design)
**Status:** Design stage — built into platform, not yet published as open standard
**Owner:** Oracle Platform

---

## What Is CPVP?

The Component Performance Verification Protocol is a structured post-installation follow-up system to capture real-world component performance data from engineers who received selection recommendations.

The engineering world has a gap: manufacturers produce excellent selection guides for new components, but nobody systematically tracks what happens after installation. Does the selected component actually perform as expected? Does it last? Would the engineer make the same choice again?

CPVP closes that gap. It transforms every Oracle consultation from a one-time transaction into a longitudinal data collection point.

---

## Why This Matters

### The Core Problem with Component Selection

Current state:
- Engineer asks "which filter should I use?" → Oracle recommends based on specs and theoretical performance
- Engineer buys and installs it → silence
- Three months later, the component fails or underperforms → this information never feeds back into future recommendations

CPVP state:
- Engineer asks → Oracle recommends
- Engineer receives 30-day check-in: "Did you install it? How is it performing?"
- Engineer receives 90-day Performance Verification: detailed performance questions
- Engineer receives 6-month/1-year Longevity Report: long-term durability data
- All of this feeds back into future recommendations

### The Appreciating Asset

Each outcome data point makes future recommendations better. This is compounding:

- 100 outcomes → Oracle knows which filters actually last in high-temperature applications
- 1,000 outcomes → Oracle can identify which manufacturers' performance claims match reality
- 10,000 outcomes → Oracle has a performance database that no manufacturer, distributor, or standards body has

This is the long-term competitive moat. Not the AI (interchangeable) — the outcome data (irreplaceable).

---

## Three-Document Structure

CPVP consists of three data collection events per consultation:

### Document 1: Installation Verification (30 days post-recommendation)

**Timing:** 30 days after the recommendation was given
**Purpose:** Confirm implementation, capture initial conditions

**Key questions:**
- Did you implement the recommendation?
- If not, why not? (budget, approvals, chose different product, problem resolved)
- What component was actually installed? (may differ from recommendation)
- What were the actual operating conditions at startup? (pressure, flow, temperature, fluid type)
- Any issues during installation or startup?
- Initial performance observations?

**Data captured:**
```
{
  "implementation_status": "implemented" | "modified" | "not_implemented" | "pending",
  "actual_component": string | null,
  "startup_conditions": {
    "pressure_bar": number | null,
    "flow_lpm": number | null,
    "temp_celsius": number | null,
    "fluid_type": string | null
  },
  "installation_issues": string | null,
  "initial_observations": string | null
}
```

### Document 2: Performance Verification (2-4 weeks after startup, or ~90 days post-recommendation)

**Timing:** After enough operating time to observe real performance (2-4 weeks of service)
**Purpose:** Capture actual vs. expected performance

**Key questions:**
- How is the component performing against your expectations?
- Is it meeting its rated specifications in your actual conditions?
- What is the measured differential pressure? (for filters) / measured flow at rated pressure? (for pumps)
- Any unexpected behavior or concerns?
- Has the system cleanliness target been achieved? (filtration verticals)
- **Would you select the same component again for this application?**

**The key question** — "Would you select the same component again?" — is the single most valuable data point CPVP collects. It's a holistic judgment that incorporates everything the engineer has experienced: installation difficulty, initial performance, reliability, cost vs. value, manufacturer support. It cannot be inferred from specifications.

**Data captured:**
```
{
  "performance_rating": 1-5,
  "performance_notes": string,
  "meets_specifications": boolean | null,
  "measured_performance": {
    "metric_name": value
    // domain-specific measurements
  },
  "unexpected_behavior": string | null,
  "would_recommend_same": boolean,
  "alternative_tried": string | null
}
```

### Document 3: Longevity Report (3, 6, or 12 months post-installation)

**Timing:** Configurable — 90, 180, or 365 days. Set based on expected component lifecycle.
**Purpose:** Capture long-term durability and failure data

**Key questions:**
- Is the component still in service?
- How many operating hours since installation?
- Has the component failed or required replacement?
- If replaced: why? What was the failure mode? What was the timeline?
- Did operating conditions change after installation?
- What modifications (if any) were made to the selection or system?
- Would you still select the same component again, knowing what you know now?
- Any other notes for the Oracle knowledge base?

**Data captured:**
```
{
  "still_in_service": boolean,
  "operating_hours": number | null,
  "failure_occurred": boolean,
  "failure_mode": string | null,
  "failure_timeline": string | null,
  "operating_conditions_matched": boolean | null,
  "operating_conditions_notes": string | null,
  "modifications_made": string | null,
  "would_recommend_same": boolean | null,
  "additional_notes": string | null
}
```

---

## The Data Model

CPVP data lives in the consultation_outcomes table (already built into the platform):

```sql
CREATE TABLE consultation_outcomes (
    id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES consultation_sessions(id),
    followup_stage TEXT,          -- '30_day', '90_day', '180_day', 'user_initiated'
    created_at TEXT,
    
    -- Implementation
    implementation_status TEXT,   -- 'implemented', 'modified', 'not_implemented', 'pending'
    
    -- Performance
    performance_rating INTEGER,   -- 1-5
    performance_notes TEXT,
    
    -- Failure tracking
    failure_occurred INTEGER,     -- boolean
    failure_mode TEXT,
    failure_timeline TEXT,
    
    -- Conditions
    operating_conditions_matched INTEGER,  -- boolean
    operating_conditions_notes TEXT,
    modifications_made TEXT,
    
    -- The key question
    would_recommend_same INTEGER,  -- boolean
    
    -- Supporting data
    alternative_tried TEXT,
    additional_notes TEXT
);
```

Follow-up schedules are created automatically when a consultation transitions from gathering to answering phase:

```python
# From backend/main.py (already implemented)
for stage, days in [("30_day", 30), ("90_day", 90), ("180_day", 180)]:
    scheduled = (now + timedelta(days=days)).isoformat()
    await database.create_followup_schedule(session_id=session_id, ...)
```

---

## Connection to the Consulting Surface

CPVP is not an add-on — it's built into the platform from day one.

**What's already built:**
- `consultation_outcomes` table in the database schema
- Outcome creation, retrieval, and update API endpoints
- Automatic follow-up scheduling on phase transition
- Training data logging for outcome events
- API endpoint for pending follow-up retrieval (`/api/consult/outcomes/pending-followups`)

**What's not yet built (future work):**
- Automated follow-up email delivery (the schedule exists; the mailer doesn't)
- CPVP-specific frontend UI (currently outcomes submitted via API)
- Outcome data visualization and aggregation dashboard
- Training pipeline integration that feeds outcomes back into retrieval weights

---

## Publication Strategy

### The "Trojan Horse" Approach

Publish CPVP as an **open standard and white paper** before Oracle launches publicly.

Why:
1. **Establishes authority** — Oracle becomes the organization that defined the standard for industrial component performance tracking
2. **Industry adoption** — If manufacturers and distributors adopt CPVP, they start collecting data in a format Oracle can ingest
3. **Network effect** — An open standard creates ecosystem participants. Oracle is the natural home for aggregated CPVP data.
4. **Positioning** — Oracle is not a chatbot. It's the company that cares enough about real-world outcomes to create a formal protocol for tracking them.

Publication format:
- White paper: "Component Performance Verification Protocol v1.0 — A Framework for Systematic Post-Installation Data Collection in Industrial Fluid System Applications"
- Target publications: Fluid Power Journal, Hydraulics & Pneumatics, NFPA (National Fluid Power Association) proceedings
- CC BY license — anyone can use it, cite Oracle as the source

### Timing

Publish CPVP before Oracle has any paying customers. The white paper establishes Oracle as a knowledge organization, not a startup. Engineers should encounter CPVP before they encounter Oracle the product.

---

## The Long Game

CPVP is how Oracle becomes an appreciating asset over time.

At launch: Oracle recommends components based on specs, standards, and application knowledge.
After 1 year: Oracle knows which components actually perform as rated in real applications.
After 3 years: Oracle knows failure modes, lifecycle data, and application-specific reliability patterns that no manufacturer has.
After 10 years: Oracle's outcome database is the most comprehensive real-world component performance dataset in industrial fluid systems.

Every Oracle consultation contributes to this dataset. Every CPVP submission makes the next recommendation better. The asset compounds.

This is not a feature. It is the strategy.
