## Architecture Overview

---

## Data Pipeline

SciCheck uses a hybrid data generation pipeline that combines real peer-reviewed scientific literature with programmatic distortion injection to produce training scenarios with perfectly deterministic ground truth.

### Domain Pool Construction

We define 40 research domains spanning nutrition, exercise science, psychology, pharmacology, and behavioral health. For each domain, a structured PubMed MeSH query filters for randomized controlled trials with open access full text, explicitly excluding review papers. This gives us a pool of PMCIDs per domain that are RCT-verified, human-subject studies with accessible full text.

### Paper Section Extraction

For each candidate PMCID, we fetch the full-text XML from PubMed Central via the NCBI E-utilities API (ESearch + EFetch against db=pmc) - free, no API key required. We extract five sections: `abstract`, `methods`, `results`, `limitations`, and `stats`. The `stats` section is not a native XML section - it's constructed programmatically by extracting all sentences from `results` that contain statistical content (percentages, p-values, confidence intervals).

Papers are filtered for usability before any further processing: they must have an abstract, a results section with statistical content, and signals consistent with a completed intervention study. Protocol papers (future-tense results, ongoing studies) are discarded at this stage.

### Press RElease Generation

The extracted sections are passed to Groq's `meta-llama/llama-4-scout-17b-16e-instruct` model to generate a faithful press release of 150–250 words. The prompt enforces past tense, lay-audience voice, specific population mention, key finding with actual magnitude, and at least one limitation. temperature=0.0 ensures determinism - identical sections always produce the same PR.

### Programmatic Distortion Engine

Distortions are applied to the generated PR text, never to the paper sections — the sections remain untouched as ground truth. Each distortion is recorded as a structured object:

```python
{
  "type": "scope_inflation",
  "original_text": "34 Finnish adults aged 60–75",
  "distorted_to": "people",
  "found_in_section": "abstract",
  "severity": "low"
}
```

`found_in_section` identifies which paper section the agent must fetch to prove the PR claim is wrong. This field directly drives reward computation and grader logic.
Distortion counts are tier-specific and deterministic per scenario:

- **Easy:** 1 distortion from {`scope_inflation`, `certainty_inflation`, `magnitude_distortion`}. Evidence always in abstract.  
- **Medium:** 1–2 distortions from {`hedging_stripped`, `population_generalized`, `causal_overclaim`, `stat_fabrication`}. Evidence requires fetching beyond abstract.  
- **Hard:** 3 distortions, always including `misleading_omission` plus 2 others. Evidence spans results and limitations.  

`misleading_omission` is structurally different from all other distortions - it modifies no text. It records what the PR silently omits (primary endpoint failure) and sets `found_in_section` to results and limitations both.

### Manual Review

After all scenarios are generated and written to `data/scenarios.json`, a manual review pass checks each PR for grammatical integrity (distortions should not produce unnatural language), and distortion detectability (evidence must actually be present in the named section).
This step is especially important to ensure the reliability on the grader. It validates that the programmatically assigned ground truth is actually correct before the scenarios are used for training or evaluation.

### Final Data Distribution

Total scenarios: 69
Easy:   38  (target: 20) - OVER by 18
Medium: 22  (target: 20) - slightly over
Hard:    9  (target: 20) - SEVERELY UNDER by 11

---

## Distortion Types

SciCheck's distortion taxonomy is designed around a core principle: every distortion must be detectable from a specific paper section. This is what makes the environment trainable rather than arbitrary. The agent is essentially investigating. Each distortion has a `found_in_section` field that points to exactly which section contains the evidence that proves the PR claim is wrong. That field drives both the reward function and the grader.

The eight distortion types map directly to documented failure modes in science journalism - patterns that have been studied in press release analysis literature. They are organized into three tiers by detection difficulty.

**Easy Tier**: Surface Overclaims

These distortions modify language that is directly verifiable from the abstract alone. An agent that fetches only the abstract has everything it needs.  

- **SCOPE_INFLATION:** It generalizes a specific study context to a broader population or setting. A study conducted "in mice" becomes "in humans." "34 Finnish adults aged 60–75" becomes "people." "A pilot study" becomes "a study." The distortion exploits the gap between what a finding actually applies to and what a lay reader assumes. Implemented via regex pattern matching on population descriptors, animal model language, and study design qualifiers.
- **CERTAINTY_INFLATION:** It upgrades hedged epistemic language to definitive claims. "May suggest" becomes "confirms." "Appeared to" becomes "is proven to." "Indicated" becomes "proved." This is the most common distortion in real science journalism - the systematic removal of uncertainty that researchers deliberately encoded. Implemented via a priority-ordered list of hedge patterns, replacing the first match found.
- **MAGNITUDE_DISTORTION:** It replaces precise quantitative language with vague amplifiers. "A modest 8% reduction" becomes "a dramatic reduction." Specific percentages are replaced with terms like "significant" or "major." This distortion is particularly insidious because it sounds more impressive while being less informative - exactly the direction real PRs tend to drift.


**Medium Tier**: Investigation-Requiring Distortions

These distortions cannot be detected from the abstract alone. The agent must fetch beyond the abstract to find the contradicting evidence - typically methods or stats sections.

- **POPULATION_GENERALIZATION:** It strips demographic specifics that appear in the methods section. "Thirty women aged 68–69" becomes "adults." The abstract may mention a finding; the methods section reveals who it actually applies to. This requires the agent to fetch methods and cross-reference the population description against the PR's claim.
- **CAUSAL_OVERCLAIM:** It converts correlation language to causation. "Associated with" becomes "causes." "Linked to" becomes "results in." "Correlated with" becomes "leads to." The evidence that the original finding was correlational typically lives in the methods section (study design) or results section (statistical language).
- **HEDGING_STRIPPED:** It removes entire sentences containing author caveats. Any sentence containing terms like "preliminary," "small sample," "further research needed," or "limitations" - along with the following sentence for context — is deleted entirely from the PR. The agent must fetch the limitations section to discover what the PR chose to omit. Unlike other distortions which modify text, this one subtracts it.e 
- **STAT_FABRICATION:** It identifies a percentage in the stats section (extracted from results - sentences containing %, p-values, or confidence intervals) and replaces it with a fabricated value inflated by a factor of 3–5×. The fabricated statistic is appended to the PR as a standalone finding. The agent must fetch the stats section and compare the reported number against what the PR claims.


**Hard Tier**: Structural Omission

- **MISLEADING_OMISSION:** It is architecturally different from every other distortion. It modifies no text in the PR. Instead, it identifies a primary endpoint failure in the results section - a pattern like "primary outcome showed no significant difference" or "failed to reach significance" - and records that this finding was never mentioned in the PR. The PR reports only a secondary or subgroup finding, and every sentence it contains is technically true. The distortion is purely what was left out.

This makes it the hardest distortion to detect. There is no wrong word to flag, no inflated number to compare. The agent must fetch the results section, notice the primary endpoint failure, fetch the limitations section to find the author's own admission, and then reason about what should have been in the PR but wasn't. The grader handles this differently from all other distortions - it checks the agent's overall verdict field (`misleading_by_omission`) rather than a specific divergence entry, because there is no PR sentence to quote as evidence.
`misleading_omission` is always present in hard scenarios, alongside two additional distortions from the medium-tier pool. The combination means the agent must both reason about omission and identify specific textual distortions - requiring the widest investigation depth of any tier.

---

## Environment Design

## Reward Function

## Grader Design

## Baseline Agent