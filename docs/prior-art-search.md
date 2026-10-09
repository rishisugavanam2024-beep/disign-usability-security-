# Preliminary Prior-Art Search: SafeRevoke

**Search date:** 5 October 2026  
**Project:** SafeRevoke / Adaptive Counterfactual Access Testing  
**Purpose:** Assess whether the implemented mechanism has a defensible technical distinction before paying for professional patent drafting.

This is a technical search, not a legal opinion, a freedom-to-operate analysis, or a guarantee that an examiner will not find additional material. Patent novelty is usually defeated when one earlier reference discloses every claimed element. Inventive step/non-obviousness may be defeated by an obvious combination of multiple references. WIPO describes that distinction in its [PCT examination guidance](https://www.wipo.int/en/web/pct-system/texts/ispe/13_01_02).

## 1. Mechanism searched

The implemented candidate mechanism has these elements:

1. Record a successful baseline workflow as provenance tuples containing the acting identity, resource, action, grant source, execution phase and output result.
2. Create a counterfactual policy state by removing a selected access grant in an isolated execution environment.
3. Execute the same approved workflow under the counterfactual state rather than merely re-evaluating its previous access requests.
4. Detect a **runtime fallback edge** when the changed execution reaches the same protected operation through a different identity or grant source.
5. Mark the fallback unsafe when its privilege/risk scope is greater than the removed path, even if the workflow output remains correct.
6. Use the observed fallback or residual-access edge to choose a follow-up multi-grant experiment, avoiding unrelated combinations.
7. Execute both discovered removal orders, score their intermediate states and recommend the lower-risk order—or require a least-privilege replacement when neither order is acceptable.
8. Separately identify work authorized before revocation that completes afterward.

The potentially protectable center is elements 4–7 as one closed-loop method. Elements 1–3 and 8 are individually well represented in prior work.

## 2. Search strategy

The search covered Google Patents, WIPO/EPO guidance, official cloud documentation and research indexes. Query groups included combinations of:

- access policy simulation, shadow policy and policy mutation;
- permission removal, revocation impact and workflow failure;
- fallback identity, fallback credential and alternative access path;
- runtime authorization provenance and execution tracing;
- adaptive test selection, dependency graph and test sequencing;
- least privilege, permission usage and automated removal;
- delayed revocation, in-flight work and policy-enforcement delay.

Relevant classifications and citation trails were followed around G06F21/60, G06F21/604, H04L63/10 and H04L63/20.

## 3. Closest patent material

| Reference | What it already teaches | Overlap | Important difference from SafeRevoke | Risk |
|---|---|---|---|---|
| [US8813170B2 — Testing access policies](https://patents.google.com/patent/US8813170) | Evaluate real requests under an effective and test policy, log different authorization decisions, and decide whether to adopt the test policy. | Counterfactual policy comparison and reporting. | It compares authorization decisions; it does not rerun application behavior after denial to discover a different identity, then derive and sequence new removal experiments. | High against broad “test before removal” claims. |
| [US10673905B1 — Service-level authorization policy management](https://patents.google.com/patent/US10673905B1/en) | A shadow policy runs alongside the active policy for a specified period; divergent authorization results are reported. | Shadow testing, comparison and reporting. | The shadow result is not supplied to the application, so it cannot observe denial-triggered application fallback behavior. | High against shadow-policy claims. |
| [US10320624B1 — Access-control policy simulation and testing](https://patents.google.com/patent/US10320624B1/en) | Sandboxed policy evaluation, contextual request simulation, reasons for denial and remediation options. | Isolated simulation and policy remediation. | It evaluates requests outside runtime; it does not execute the workflow under the changed policy or construct fallback-derived removal sequences. | High against generic sandbox/simulation claims. |
| [US11449618B2 — Active testing of access-control policy](https://patents.google.com/patent/US11449618B2/en) | Insert probing logic, attempt forbidden operations and monitor predetermined side effects to detect compromise. | Active security probes and behavior monitoring. | It probes forbidden operations for intrusion detection, rather than removing a grant, discovering an unplanned substitute identity and planning revocation order. | Medium. |
| [US9288232B2 — Reconciling permission usage with security policy](https://patents.google.com/patent/US9288232B2/en) | Map permissions to policy items, correlate usage, identify redundant/over-permissive rules and examine whether removal changes the applied policy item or access decision. | Grant-source mapping, redundant paths and least-privilege optimization. | It analyzes policy decisions and logs, not post-denial application control flow or adaptive sequence experiments. | High against permission-source and residual-path claims. |
| [US20240411905A1 — Access privilege removal based on usage monitoring](https://patents.google.com/patent/US20240411905A1/en) | Aggregate permission use, identify underused access, consult a privilege graph and remove permissions while attempting not to affect other privileges. | Automated privilege removal, usage evidence and a privilege graph. | It is usage-threshold driven and does not actively execute permission-denial experiments or detect privileged fallback behavior. | High against generic automated-removal claims. |
| [US11388163B2 — Least-privilege resource permission management](https://patents.google.com/patent/US11388163B2/en) | Identity-resource-permission graphs and future-use prediction to derive minimum permissions. | Permission graphs and least privilege. | Prediction from historical/similar identities differs from counterfactual execution and fallback-derived ordering. | Medium. |
| [US7480900B1 — Adaptive software testing](https://patents.google.com/patent/US7480900B1/en) | Build a graph connecting tests to executed components and use the graph to select or schedule relevant tests. | Runtime-derived graph and adaptive test selection. | It is general code-coverage testing, not authorization mutation or removal-order risk. | Medium-to-high for arguing that adaptive selection itself is inventive. |
| [CN110650139B — Cloud resource access control](https://patents.google.com/patent/CN110650139B/en) | Identify indirect authorization chains and revoke in a preset back-to-front hierarchical order. | Permission dependencies and revocation order. | The order follows a known delegation hierarchy; it is not discovered from application behavior after a denial, and both orders are not experimentally scored. | Medium-to-high against generic “revocation sequence” claims. |
| [CN119996084A — Dynamic network-access rights based on behavior](https://patents.google.com/patent/CN119996084A/en) | Build an authority dependency graph with hidden paths, generate an alternative access path and lower authority based on interruption probability. | Hidden dependency paths, alternate paths and privilege levels. | It creates an alternative interface path for continuity rather than detecting an application's credential fallback through permission-removal experiments. | Medium; requires professional review because its vocabulary is close. |
| [US12238106B1 — Troubleshooting policy-based permissions](https://patents.google.com/patent/US12238106B1/en) | Identify policies that allow unintended access and suggest removing allows or adding denies. | Remediation of alternate policy allowances. | It reasons over policies, not workflow execution or removal-order testing. | Medium. |

## 4. Closest non-patent material and products

| Reference | Existing capability | Distinction |
|---|---|---|
| [Margrave: Verification and change-impact analysis of access-control policies](https://explore.openaire.eu/search/publication?pid=10.1145/1062455.1062502) | Semantic differencing between policy versions using decision diagrams. | Policy semantics, not changed application behavior after a real denial. |
| [ACCESSPROV](https://www.usenix.org/conference/tapp17/workshop-program/presentation/capobianco) | Runtime provenance hooks for inputs affecting access-control decisions. | Provenance detects enforcement flaws; it does not perform grant-removal mutations or generate revocation sequences. |
| [NIST Practical Combinatorial Testing](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-142.pdf) | Covering arrays and sequence-covering arrays reduce combinations and cover event orders. | SafeRevoke's test-space reduction must be specifically tied to fallback edges; “test combinations efficiently” is already known. |
| [Testing obligation-policy enforcement using mutation analysis](https://orbilu.uni.lu/handle/10993/26423) | Mutation operators inject minimal policy errors to assess enforcement tests. | It supports permission mutation as known art, not the fallback-edge feedback loop. |
| [AWS IAM Access Analyzer](https://docs.aws.amazon.com/us_en/IAM/latest/UserGuide/access-analyzer-policy-generation.html) | Builds narrower policy templates from historical CloudTrail activity. | It does not execute the application after removing a permission or observe alternate credentials. |
| [Google Cloud Policy Simulator](https://docs.cloud.google.com/policy-intelligence/docs/iam-simulator-overview) | Replays up to 90 days of access attempts under current and proposed allow policies. | It re-evaluates recorded attempts; it does not generate new control flow caused by a denial. |
| [Real-time update of access-control policies](https://www.sciencedirect.com/science/article/abs/pii/S0169023X03001782) | Studies policy changes during long-running transactions and immediate enforcement. | This substantially weakens a broad claim to detecting post-revocation/in-flight work. |

## 5. Element-by-element assessment

| Candidate element | Preliminary assessment |
|---|---|
| Isolated permission-removal testing | Not new by itself. |
| Baseline versus mutated result comparison | Not new by itself. |
| Identity/resource/action/grant provenance | Not new by itself. |
| Discover that effective access remains through another policy or role | Not new by itself. |
| Execute the application under a denied permission and observe a different identity perform the same protected operation | No exact earlier disclosure located in this search; promising but narrow. |
| Compare the fallback identity's effective privilege scope with the baseline identity | Risk scoring is known generally; the comparison must be technically precise. |
| Create a fallback edge directly from the paired baseline/mutated traces | No exact disclosure located; strongest candidate detail. |
| Select the next permission mutation from that newly observed edge | Adaptive selection is known generally, but this authorization-specific feedback rule may distinguish the method. |
| Test both removal orders and score intermediate security/availability states | Sequence testing and preset revocation ordering are known; deriving the pair from runtime fallback evidence is the potentially distinguishing link. |
| Detect queued work that finishes after revocation | Known problem area; weak as the main inventive concept. |

## 6. Preliminary conclusion

### Novelty

No single reference found in this search discloses all of the following together:

> permission-removal execution → changed-principal provenance → higher-privilege fallback edge → edge-selected follow-up mutation → bidirectional removal-order scoring.

That is encouraging, but it is not proof of novelty. Different terminology, non-English documents, unpublished applications and documents outside the searched databases may still exist.

### Inventive step / non-obviousness

The risk is significant. An examiner could combine:

1. shadow or sandbox policy testing;
2. runtime access-decision provenance;
3. permission/delegation graphs;
4. adaptive or combinatorial test selection; and
5. sequence-aware revocation.

WIPO guidance permits multiple references to be combined when the combination would have been obvious. The application therefore needs more than a collection of these features.

### Current assessment

- **Broad concept — “test permissions before removal”: very weak.**
- **Broad concept — “find alternate paths and recommend removal order”: weak to uncertain.**
- **Narrow closed-loop trace-difference mechanism: potentially defensible, but unproven.**
- **Patent filing readiness today: not ready.** The algorithm and comparative evidence need strengthening first.

## 7. Candidate technical claim center

A future independent claim should focus on a computer-implemented method that:

1. executes a workflow under a first authorization state and stores an ordered provenance trace;
2. executes the same workflow under a second state in which a selected grant is disabled;
3. aligns protected-operation events between the traces by resource, action and workflow-output checkpoint;
4. detects that an aligned operation is performed through a second principal or grant source absent from the first trace;
5. computes a privilege-scope increase for that second path;
6. creates a directed fallback edge from the disabled grant to the observed grant source;
7. selects, from that edge rather than from the full grant Cartesian product, a second mutation experiment;
8. runs both orders of the connected mutations and evaluates security and workflow invariants after each intermediate state; and
9. outputs either a lower-risk transition order or a requirement for a restricted replacement identity.

Terms such as “risk,” “same operation,” “workflow correctness,” “fallback,” and “lower-risk” must be defined as machine-computable values, not administrator opinion.

## 8. Work needed before professional review

1. **Implemented:** replace manually assigned grant-risk numbers with an effective privilege-scope calculation over reachable `(resource, action)` pairs.
2. **Implemented:** align traces by semantic checkpoint, resource, action and occurrence so denied retries and reordered independent events do not prevent matching.
3. Formalize security invariants and output checkpoints supplied by the workflow owner.
4. **Implemented for the synthetic suite:** the adaptive benchmark recovers all five planted interactions with 27 experiments versus 115 for exhaustive ordered-pair testing, a 76.52% reduction. A real-system benchmark is still required.
5. **Implemented for the synthetic suite:** three independent applications are compared directly with policy-only request replay. SafeRevoke finds 5/5 planted interactions; replay finds 2/5 and 0/3 cross-identity runtime fallbacks.
6. Search the final claim language in Google Patents, WIPO PATENTSCOPE, Espacenet and the intended filing jurisdiction.
7. Have a registered patent professional review the closest references, particularly US8813170B2, US10673905B1, US9288232B2, US7480900B1, CN110650139B and CN119996084A.

## 9. Decision

Continue the project only around the narrow closed-loop fallback mechanism. Do not describe policy simulation, permission graphs, access-history analysis, generic mutation testing or generic removal sequencing as the invention. The next engineering milestone should validate the mechanism on several independent applications and compare it directly with policy-only request replay.

### Prototype update

The first two engineering milestones are now implemented. In the company-portal lab, the dedicated report identity reaches one capability with impact score 1, while the observed fallback identity reaches seven capabilities with impact score 11. Semantic trace alignment identifies the fallback even though a denied retry is inserted before it.

The comparative suite contains a company portal, incident-response console and document-publishing service. Across five planted interactions, SafeRevoke reports 5/5, while policy-only request replay reports 2/5 and misses all three cross-identity runtime fallbacks. Adaptive selection runs 27 experiments rather than 115 exhaustive experiments. This demonstrates the mechanism under controlled conditions; because the applications and faults are synthetic, it is not yet evidence of production effectiveness or patentability.
