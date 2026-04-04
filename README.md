---
title: SciCheck
emoji: 🔬
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
---

# SciCheck: A Scientific Claim Verification Environment for LLM Agents

In today's world, where fact-checking has become a rare event, it's important to ponder what their origin is. Talking specifically about science misinformations - they hardly originate in tabloids, rather in a press release. Then journalists copy them verbatim, and public reads only the headlines. Nobody goes back to the paper.

SciCheck is a multi-step investigation environment where an AI agent must run a fact-check: firstly, read the press release, then systematically investigate the underlying research to find where the science was lost in translation, and what is the "real finding" - if at all.

---

## Core Premise

The agent receives only a press release. It cannot see the paper. Through a series of investigative tools - fetching the abstract, methods, results, limitations and statistics - it must reconstruct what the research actually found and identify every point where the PR overstates, misinterprets or silently omits. Press releases in SciCheck are procedurally generated from real PubMed abstracts with programmatically applied distortions, giving the environment infinite unique episodes with perfectly deterministic ground truth.

---

## Setup & Usage