# PIT TEST REPORT

Status: PASS
Date: 2026-10-01

Executed by GitHub Actions matrix run:
36765636994

PIT tests passed:
- future/unpublished OI is rejected from a historical decision
- available OI is accepted
- naive decision time is rejected

Invariant:
availability_time <= decision_time

Scope:
This validates the canonical PIT data model and filter logic. It does not yet prove
that the production CME ingestion layer populates availability_time correctly.
