# Insurance Fraud Detection System
## Business User Guide & Demo Manual

---

# Table of Contents

1. [Executive Overview](#1-executive-overview)
2. [Understanding the Data Model](#2-understanding-the-data-model)
3. [Fraud Patterns Explained](#3-fraud-patterns-explained)
4. [Detection Algorithms & Sensitivity](#4-detection-algorithms--sensitivity)
5. [Using the Application](#5-using-the-application)
6. [Demo Scenarios](#6-demo-scenarios)
7. [Glossary](#7-glossary)

---

# 1. Executive Overview

## What is This Tool?

This application demonstrates how **graph database technology** can revolutionize insurance fraud detection. Unlike traditional systems that analyze claims in isolation, this tool maps relationships between all entities—claimants, witnesses, medical providers, attorneys, body shops, and adjusters—to uncover hidden fraud networks.

## The Problem We Solve

Insurance fraud costs the industry **$80+ billion annually** in the US alone. Traditional detection methods catch obvious cases but miss sophisticated fraud rings where:
- The same "witnesses" appear across multiple unrelated accidents
- Certain attorneys consistently refer clients to the same body shops
- Medical providers bill for an unusually high volume of similar claims
- Adjusters show suspicious patterns with specific service providers

## Our Approach

By representing insurance data as a **network graph**, we can:

| Traditional Approach | Graph-Based Approach |
|---------------------|---------------------|
| Analyze claims individually | See connections across claims |
| Rule-based flags | Pattern-based detection |
| Miss coordinated fraud | Expose fraud rings |
| Reactive investigation | Proactive risk scoring |

---

# 2. Understanding the Data Model

## Entity Types (Nodes)

The system models the insurance ecosystem with these core entities:

### Core Entity
| Entity | Description | Key Attributes |
|--------|-------------|----------------|
| **Claim** | An insurance claim filed | ID, Amount, Date, Type, Fraud Status |

### People
| Entity | Description | Key Attributes |
|--------|-------------|----------------|
| **Claimant** | Person who files the claim | Name, SSN, Phone |
| **Witness** | Person who witnessed the incident | Name, Phone |
| **Adjuster** | Company employee handling the claim | Name, Employee ID |

### Service Providers
| Entity | Description | Key Attributes |
|--------|-------------|----------------|
| **Medical Provider** | Hospital, clinic, or doctor | Name, License |
| **Attorney** | Legal representation | Name, Bar Number |
| **Body Shop** | Auto repair facility | Name, License |

## Relationships (Edges)

Entities are connected through these relationships:

```
                    ┌──────────────┐
                    │    Claim     │
                    └──────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
         ▼                 ▼                 ▼
    ┌─────────┐      ┌─────────┐      ┌─────────┐
    │FILED_BY │      │HANDLED_ │      │WITNESSED│
    │         │      │   BY    │      │   _BY   │
    └────┬────┘      └────┬────┘      └────┬────┘
         │                │                │
         ▼                ▼                ▼
    ┌─────────┐      ┌─────────┐      ┌─────────┐
    │Claimant │      │Adjuster │      │ Witness │
    └─────────┘      └─────────┘      └─────────┘


         ┌──────────────┐
         │    Claim     │
         └──────────────┘
                │
    ┌───────────┼───────────┐
    │           │           │
    ▼           ▼           ▼
┌────────┐ ┌────────┐ ┌────────┐
│TREATED │ │REPAIRED│ │REPRES- │
│  _AT   │ │  _AT   │ │ENTED_BY│
└───┬────┘ └───┬────┘ └───┬────┘
    │          │          │
    ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐
│Medical │ │ Body   │ │Attorney│
│Provider│ │ Shop   │ │        │
└────────┘ └────────┘ └────────┘
```

### Relationship Types

| Relationship | From | To | Meaning |
|--------------|------|-----|---------|
| `FILED_BY` | Claim | Claimant | Who submitted the claim |
| `HANDLED_BY` | Claim | Adjuster | Company employee assigned |
| `WITNESSED_BY` | Claim | Witness | Observer of the incident |
| `TREATED_AT` | Claim | Medical Provider | Where medical treatment occurred |
| `REPAIRED_AT` | Claim | Body Shop | Where vehicle was repaired |
| `REPRESENTED_BY` | Claim | Attorney | Legal representation |
| `KNOWS` | Person | Person | Social connection (used in phantom passenger detection) |

---

# 3. Fraud Patterns Explained

The system detects five distinct fraud patterns, each representing a real-world scheme.

## 3.1 Medical Mill 🏥

### What Is It?
A "medical mill" is a healthcare provider that processes an unusually high volume of insurance claims, often with inflated billing. These facilities may:
- Perform unnecessary procedures
- Bill for services never rendered
- Operate as fronts for organized fraud rings

### Network Signature
```
              ┌─────────┐
              │ Medical │
              │Provider │ ← HIGH CLAIM VOLUME
              └────┬────┘
                   │
     ┌─────────────┼─────────────┐
     │             │             │
     ▼             ▼             ▼
┌─────────┐  ┌─────────┐  ┌─────────┐
│ Claim 1 │  │ Claim 2 │  │ Claim 3 │  ... (many more)
│ $25,000 │  │ $30,000 │  │ $28,000 │
└─────────┘  └─────────┘  └─────────┘
```

### Red Flags
- Provider has significantly more claims than peers
- Higher-than-average claim amounts
- Claims clustered in short time periods

---

## 3.2 Body Shop Kickback 🔧

### What Is It?
An attorney and body shop collude to defraud insurance companies. The attorney steers clients to a specific body shop in exchange for referral fees (kickbacks). Both parties benefit:
- Attorney gets kickback payments
- Body shop gets guaranteed business and may inflate repair costs

### Network Signature
```
┌──────────┐                    ┌──────────┐
│ Attorney │◄──── KICKBACK ────►│Body Shop │
└────┬─────┘                    └────┬─────┘
     │                               │
     │ REPRESENTED_BY          REPAIRED_AT
     │                               │
     ▼                               ▼
┌─────────┐  ┌─────────┐  ┌─────────┐
│ Claim 1 │  │ Claim 2 │  │ Claim 3 │
└─────────┘  └─────────┘  └─────────┘
        ↖         │         ↗
         Same attorney-body shop pair
              on multiple claims
```

### Red Flags
- Same attorney-body shop pair appears on multiple claims
- Pattern persists over time
- Claims may have similar characteristics

---

## 3.3 Staged Accident 🚗

### What Is It?
A group of conspirators deliberately cause or fake accidents to collect insurance payouts. The same people appear as claimants and witnesses across multiple "accidents."

### Network Signature
```
        ┌─────────┐         ┌─────────┐
        │Person A │◄───────►│Person B │
        └────┬────┘  KNOWS  └────┬────┘
             │                    │
    ┌────────┴────────┐  ┌───────┴────────┐
    │                 │  │                │
    ▼                 ▼  ▼                ▼
┌─────────┐      ┌─────────┐      ┌─────────┐
│ Claim 1 │      │ Claim 2 │      │ Claim 3 │
│Claimant:│      │Claimant:│      │Claimant:│
│Person A │      │Person B │      │Person A │
│Witness: │      │Witness: │      │Witness: │
│Person B │      │Person A │      │Person B │
└─────────┘      └─────────┘      └─────────┘

Same people swap roles across claims!
```

### Red Flags
- Same individuals appear together on multiple claims
- Roles swap (claimant becomes witness, vice versa)
- Claims filed within similar timeframes
- Similar accident descriptions

---

## 3.4 Phantom Passenger 👻

### What Is It?
A fraudster adds fictitious passengers to accident claims. These "phantom passengers" file their own claims for injuries they never sustained. They're often connected through social networks.

### Network Signature
```
                ┌──────────────┐
                │Main Claimant │
                │   (Real)     │
                └──────┬───────┘
                       │
          ┌────────────┼────────────┐
          │            │            │
        KNOWS        KNOWS        KNOWS
          │            │            │
          ▼            ▼            ▼
     ┌─────────┐ ┌─────────┐ ┌─────────┐
     │Phantom 1│ │Phantom 2│ │Phantom 3│
     └────┬────┘ └────┬────┘ └────┬────┘
          │           │           │
          ▼           ▼           ▼
     ┌─────────┐ ┌─────────┐ ┌─────────┐
     │ Claim 1 │ │ Claim 2 │ │ Claim 3 │
     └─────────┘ └─────────┘ └─────────┘

Multiple connected people filing separate claims
```

### Red Flags
- Claimant has many KNOWS connections to other claimants
- Connected individuals file claims in similar timeframes
- Claims reference similar incidents
- High claim volumes from connected network

---

## 3.5 Adjuster-Provider Collusion 👔

### What Is It?
A corrupt insurance adjuster conspires with a medical provider. The adjuster consistently approves claims from a specific provider (often expedited and without proper review) in exchange for kickbacks.

### Network Signature
```
┌──────────┐                    ┌──────────┐
│ Adjuster │◄──── COLLUSION ───►│ Medical  │
│          │                    │ Provider │
└────┬─────┘                    └────┬─────┘
     │                               │
     │ HANDLED_BY              TREATED_AT
     │                               │
     ▼                               ▼
┌─────────┐  ┌─────────┐  ┌─────────┐
│ Claim 1 │  │ Claim 2 │  │ Claim 3 │
└─────────┘  └─────────┘  └─────────┘
        ↖         │         ↗
       Same adjuster-provider pair
           handles multiple claims
```

### Red Flags
- Adjuster handles unusually high number of claims from one provider
- Claims may be approved faster than average
- Higher approval rates for that provider
- Pattern persists over time

---

# 4. Detection Algorithms & Sensitivity

## How Detection Works

The system uses **graph traversal algorithms** to identify suspicious patterns. Each algorithm queries the network for specific structural signatures.

## Detection Parameters

Each fraud type has a **sensitivity threshold** that you can adjust:

### Medical Mill Detection

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_claims` | 5 | Minimum claims at a provider to flag |
| `min_avg_amount` | $15,000 | Minimum average claim amount |

**Detection Query Logic:**
```
Find: Medical Providers with claim_count ≥ threshold
      AND average_claim_amount > min_avg_amount
Flag: Provider + all associated claims
Score: Based on claim count and average amount
```

**Tuning Guidance:**
- **Lower threshold (3-4)**: Catches borderline cases, more false positives
- **Default (5)**: Balanced detection
- **Higher threshold (7+)**: Only obvious fraud mills, fewer false positives

---

### Body Shop Kickback Detection

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_shared_claims` | 3 | Minimum shared claims between attorney-body shop pair |

**Detection Query Logic:**
```
Find: (Attorney) ← [REPRESENTED_BY] ← (Claim) → [REPAIRED_AT] → (BodyShop)
      WHERE shared_claims ≥ threshold
Flag: Attorney + Body Shop + all shared claims
Score: shared_claims × 15 (max 100)
```

**Tuning Guidance:**
- **Lower threshold (2)**: Catches emerging patterns
- **Default (3)**: Established relationships
- **Higher threshold (5+)**: Only prolific schemes

---

### Staged Accident Detection

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_shared_claims` | 2 | Minimum claims where same people appear together |

**Detection Query Logic:**
```
Find: (Person A) appears with (Person B) on multiple claims
      WHERE shared_claim_count ≥ threshold
      AND claim_type = 'Auto'
Flag: Both persons + all shared claims
Score: shared_claims × 25 (max 100)
```

**Tuning Guidance:**
- **Threshold 2**: Catches pairs appearing twice (could be coincidence)
- **Threshold 3+**: More confidence in deliberate staging

---

### Phantom Passenger Detection

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_connections` | 3 | Minimum KNOWS connections to other claimants |

**Detection Query Logic:**
```
Find: (Claimant) - [KNOWS] - (Other Claimants)
      WHERE connection_count ≥ threshold
      AND all connected persons have filed claims
Flag: Central person + connected claims
Score: connection_count × 20 (max 100)
```

**Tuning Guidance:**
- **Lower threshold (2)**: May flag legitimate family connections
- **Default (3)**: Suspicious network activity
- **Higher threshold (5+)**: Clear fraud ring hub

---

### Adjuster-Provider Collusion Detection

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_shared_claims` | 4 | Minimum claims where same adjuster handles same provider's claims |

**Detection Query Logic:**
```
Find: (Adjuster) ← [HANDLED_BY] ← (Claim) → [TREATED_AT] → (Provider)
      WHERE shared_claims ≥ threshold
Flag: Adjuster + Provider + all shared claims
Score: shared_claims × 12 (max 100)
```

**Tuning Guidance:**
- **Lower threshold (3)**: Early warning signals
- **Default (4)**: Suspicious pattern
- **Higher threshold (6+)**: Clear collusion evidence

---

## Understanding Risk Scores

Flagged entities receive a **suspicion score** from 0-100:

| Score Range | Risk Level | Visual Indicator | Recommended Action |
|-------------|------------|------------------|-------------------|
| 80-100 | Critical | Dark Orange, Large | Immediate investigation |
| 60-79 | High | Orange, Medium-Large | Priority review |
| 40-59 | Medium | Amber, Medium | Scheduled review |
| 20-39 | Low | Yellow, Small-Medium | Monitor |
| 0-19 | Minimal | Base color, Small | Normal processing |

---

# 5. Using the Application

## Navigation

The application has four main pages accessible from the sidebar:

1. **Network Discovery** - Explore entity relationships
2. **Fraud Ring Visualization** - View known fraud and run detection
3. **New Claim** - Submit claims and assess risk
4. **Admin Panel** - Generate data and manage database

---

## 5.1 Network Discovery Page

### Purpose
Explore the network starting from any entity to understand its connections.

### How to Use

1. **Select Entity Type**: Choose from Claim, Claimant, Adjuster, etc.
2. **Select Entity**: Pick a specific entity from the dropdown
3. **Set Hops**: Number of relationship levels to traverse (1-5)
4. **Apply Filters**: Choose which entity types to display
5. **Click "Explore Network"**: Visualize the network

### Reading the Visualization

| Visual Element | Meaning |
|----------------|---------|
| ⭐ Star shape | Selected/root entity |
| 🔴 Red node | Confirmed fraud |
| 🟠 Orange node | Suspicious (algorithm-flagged) |
| Node size | Larger = higher risk |
| Lines | Relationships between entities |

### Interaction Controls
- **Scroll**: Zoom in/out
- **Drag background**: Pan view
- **Drag node**: Reposition
- **Hover**: View entity details

---

## 5.2 Fraud Ring Visualization Page

### Tab 1: Known Fraud Rings

View explicitly labeled fraud patterns in the data.

**Steps:**
1. Select fraud type (Medical Mill, Kickback, etc.)
2. Choose specific ring from the list
3. Adjust neighborhood hops (1-4)
4. Click "Visualize Selected Ring"

### Tab 2: Fraud Detection

Run detection algorithms to find **unlabeled** suspicious patterns.

**Steps:**
1. Expand "Detection Parameters" to adjust thresholds
2. Click "Run Fraud Detection"
3. Review summary cards showing counts per fraud type
4. Explore detailed findings in tabs
5. Select entities to visualize their networks

---

## 5.3 New Claim Page

### Purpose
Submit new claims and assess fraud risk based on connected entities.

### Sections

**Section 1: Incident Details**
- Claim amount
- Incident date
- Incident type (Rear-End, Side Impact, etc.)

**Section 2: Involved Parties**
- Claimant (new or existing)
- Witness (optional)
- Adjuster (from company pool)

**Section 3: Service Providers**
- Medical Provider (optional)
- Body Shop (optional)
- Attorney (optional)

**Section 4: Risk Assessment Preview**
Live risk scoring based on selected entities' neighborhoods.

**Section 5: Submit**
Create the claim and visualize its network.

### Risk Indicators in Dropdowns
- 🔴 = Confirmed fraud entity
- 🟠 = Suspicious entity

### Risk Score Interpretation
| Score | Level | Meaning |
|-------|-------|---------|
| 70-100 | HIGH | Multiple fraud/suspicious connections |
| 40-69 | MEDIUM | Some concerning connections |
| 1-39 | LOW | Minor concerns |
| 0 | CLEAN | No fraud indicators |

---

## 5.4 Admin Panel

### Database Statistics
View counts of all entity types, fraud claims, and relationships.

### Data Generation

Generate synthetic data with configurable parameters:

**Legitimate Data:**
- Number of legitimate claims (50-500)

**Explicit Fraud Rings (Labeled):**
- Medical Mill rings
- Kickback rings
- Staged Accident rings
- Phantom Passenger rings
- Adjuster Collusion rings

**Implicit Fraud (Unlabeled - for detection testing):**

Three tiers per fraud type:
| Tier | Description | Detection |
|------|-------------|-----------|
| Tier 1 (Borderline) | At/below default thresholds | Only with lowered sensitivity |
| Tier 2 (Moderate) | Above thresholds | At default settings |
| Tier 3 (Obvious) | High values | Always detected |

**Near-Miss Legitimate:**
Patterns that look suspicious but are legitimate (tests false positive rates):
- High-volume providers (busy ERs)
- Repeat referrals (legitimate attorney-shop relationships)
- Repeat witnesses (family members)

### Database Management
- **Clear All Data**: Delete everything
- **Clear Detection Flags**: Remove suspicious flags while keeping data

---

# 6. Demo Scenarios

## Scenario 1: Discovering a Medical Mill

**Objective:** Show how graph analysis exposes a high-volume fraudulent provider.

**Steps:**
1. Go to **Network Discovery**
2. Select Entity Type: `MedicalProvider`
3. Find a provider with "Fraud" in the name or high claim count
4. Set Hops to 2
5. Click "Explore Network"
6. Observe the star-shaped pattern with many connected claims

**Talking Points:**
- "Notice how this provider has an unusually high number of claims radiating from it"
- "The red color indicates confirmed fraud"
- "In a real system, this pattern would trigger investigation"

---

## Scenario 2: Uncovering a Kickback Scheme

**Objective:** Demonstrate attorney-body shop collusion detection.

**Steps:**
1. Go to **Fraud Ring Visualization** → **Known Fraud Rings**
2. Select "Body Shop Kickback"
3. Choose a ring and visualize
4. Point out the attorney-body shop connection with multiple shared claims

**Talking Points:**
- "This attorney and body shop appear together on multiple claims"
- "The REFERS_TO relationship represents the suspected kickback"
- "Traditional systems see individual claims; graph sees the pattern"

---

## Scenario 3: Running Detection on Unlabeled Data

**Objective:** Show the algorithm finding hidden fraud.

**Steps:**
1. Go to **Admin Panel**
2. Generate data with Tier 2/3 implicit fraud patterns
3. Go to **Fraud Ring Visualization** → **Fraud Detection**
4. Run detection with default parameters
5. Review findings and visualize flagged entities

**Talking Points:**
- "These patterns weren't labeled as fraud in the data"
- "The algorithm found them through network analysis"
- "Adjusting thresholds lets investigators tune sensitivity"

---

## Scenario 4: Real-Time Risk Assessment

**Objective:** Demonstrate new claim risk scoring.

**Steps:**
1. Go to **New Claim**
2. Fill in incident details
3. Select an existing claimant with 🟠 flag
4. Add a suspicious body shop
5. Observe the live risk score update
6. Submit and view network

**Talking Points:**
- "Before the claim is even submitted, we can assess risk"
- "The system checks the 2-hop neighborhood of all selected entities"
- "This enables proactive fraud prevention, not just detection"

---

## Scenario 5: False Positive Testing

**Objective:** Show the system doesn't flag everything suspicious-looking.

**Steps:**
1. Generate data with "Near-Miss Legitimate" patterns
2. Run detection with default thresholds
3. Show that legitimate high-volume providers aren't flagged
4. Explain the threshold tuning concept

**Talking Points:**
- "Not every busy provider is a fraud mill"
- "The system uses thresholds to balance detection vs. false positives"
- "Investigators can adjust sensitivity based on their risk tolerance"

---

# 7. Glossary

| Term | Definition |
|------|------------|
| **Entity** | A node in the graph (person, claim, provider, etc.) |
| **Relationship** | A connection between two entities |
| **Hop** | One step along a relationship in the graph |
| **Fraud Ring** | A group of connected entities involved in coordinated fraud |
| **Explicit Fraud** | Labeled/confirmed fraud (is_fraud = true) |
| **Implicit Fraud** | Unlabeled suspicious patterns for algorithms to detect |
| **Suspicion Score** | 0-100 rating of fraud likelihood |
| **Graph Traversal** | Following relationships to explore connected entities |
| **Medical Mill** | High-volume healthcare provider fraud scheme |
| **Kickback** | Payment for referrals between attorney and body shop |
| **Staged Accident** | Deliberately caused/faked accident for insurance payout |
| **Phantom Passenger** | Fictitious person added to claim for additional payout |
| **Adjuster Collusion** | Corrupt adjuster conspiring with provider |
| **False Positive** | Legitimate pattern incorrectly flagged as suspicious |
| **Threshold** | Minimum value required to trigger detection |
| **Tier** | Level of fraud pattern intensity (Borderline/Moderate/Obvious) |

---

# Document Information

| Item | Details |
|------|---------|
| **Application** | Insurance Fraud Detection System |
| **Version** | 1.0 |
| **Technology** | Streamlit + Neo4j Graph Database |
| **Audience** | Business users, Demo presenters |

---

*This guide is intended for demonstration purposes. The synthetic data and fraud patterns are illustrative and do not represent actual insurance fraud cases.*
