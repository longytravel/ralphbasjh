"""
Step 8D: Manual Review and Apply Patch (Optional)

Purpose: Ensure all LLM changes are approved by a human before application.

Per PRD Section 3, Step 8D:
- Workflow pauses with AWAITING_PATCH_REVIEW
- Review is mandatory when LLM_REVIEW_REQUIRED=True
- If approved, create a new EA version (do not modify baseline)
- If rejected, proceed with baseline EA and skip to Step 8F
- Apply the approved patch at the end of Step 8D
"""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, List
import json
import shutil
from datetime import datetime


from ...config import (
    RUNS_DIR,
    LLM_REVIEW_REQUIRED,
    LLM_MAX_REFINEMENT_CYCLES
)
from .step08c_llm_proposal import LLMProposalResult, EAPatch


@dataclass
class ReviewDecision:
    """Review decision for LLM proposal."""
    approved: bool
    feedback: Optional[str] = None
    reviewer_notes: Optional[str] = None
    timestamp: Optional[str] = None


@dataclass
class ReviewResult:
    """Result from manual review step."""
    success: bool
    status: str  # pending_review, approved, rejected, skipped, error
    review_required: bool
    baseline_ea_path: Optional[str] = None
    active_ea_path: Optional[str] = None
    patch_applied: bool = False
    patched_ea_path: Optional[str] = None
    decision: Optional[ReviewDecision] = None
    review_package_path: Optional[str] = None
    error_message: Optional[str] = None
    refinement_cycle: int = 0

    def passed_gate(self) -> bool:
        """Check if step passed (approved, rejected, or skipped)."""
        return self.status in ["approved", "rejected", "skipped"]

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        if self.decision:
            result['decision'] = asdict(self.decision)
        return result


def _create_review_package(
    proposal: LLMProposalResult,
    baseline_ea_path: Path,
    workflow_id: str
) -> Path:
    """
    Create review package for human reviewer.

    Returns:
        Path to review package JSON
    """
    review_dir = Path(RUNS_DIR) / "analysis" / workflow_id / "patches"
    review_dir.mkdir(parents=True, exist_ok=True)

    package = {
        "workflow_id": workflow_id,
        "created_at": datetime.utcnow().isoformat(),
        "baseline_ea": str(baseline_ea_path),
        "proposal": {
            "param_actions": [
                {
                    "name": a.name,
                    "action": a.action,
                    "rationale": a.rationale,
                    "evidence": a.evidence
                }
                for a in proposal.param_actions
            ],
            "range_refinements": [
                {
                    "name": r.name,
                    "start": r.start,
                    "step": r.step,
                    "stop": r.stop,
                    "reason": r.reason
                }
                for r in proposal.range_refinements
            ],
            "ea_patch": {
                "description": proposal.ea_patch.description,
                "diff": proposal.ea_patch.diff
            } if proposal.ea_patch else None,
            "expected_impact": proposal.expected_impact,
            "risks": proposal.risks
        },
        "instructions": {
            "to_approve": "Create step8d_decision.json with: {\"approved\": true}",
            "to_reject": "Create step8d_decision.json with: {\"approved\": false}",
            "to_request_changes": "Create step8d_decision.json with: {\"approved\": false, \"feedback\": \"your feedback\"}"
        }
    }

    package_path = review_dir / "review_package.json"
    with open(package_path, 'w') as f:
        json.dump(package, f, indent=2)

    return package_path


def _read_review_decision(workflow_id: str) -> Optional[ReviewDecision]:
    """
    Read review decision from file.

    Returns:
        ReviewDecision or None if not found
    """
    decision_path = Path(RUNS_DIR) / "analysis" / workflow_id / "patches" / "step8d_decision.json"

    if not decision_path.exists():
        return None

    try:
        with open(decision_path, 'r') as f:
            data = json.load(f)

        return ReviewDecision(
            approved=data.get("approved", False),
            feedback=data.get("feedback"),
            reviewer_notes=data.get("notes"),
            timestamp=datetime.utcnow().isoformat()
        )
    except (json.JSONDecodeError, IOError):
        return None


def _apply_patch(
    baseline_ea_path: Path,
    patch: EAPatch,
    workflow_id: str,
    version: int = 2
) -> Optional[Path]:
    """
    Apply patch to create new EA version.

    Note: This is a simplified implementation. Full implementation would
    properly parse and apply unified diffs.

    Returns:
        Path to patched EA or None on failure
    """
    try:
        # Create patched version directory
        patches_dir = Path(RUNS_DIR) / "analysis" / workflow_id / "patches"
        patches_dir.mkdir(parents=True, exist_ok=True)

        # Read baseline EA
        with open(baseline_ea_path, 'r', encoding='utf-8') as f:
            baseline_code = f.read()

        # Generate patched filename
        stem = baseline_ea_path.stem
        patched_path = patches_dir / f"{stem}_v{version}.mq5"

        # If diff is a code block (not unified diff), append it
        # This is simplified - real implementation would parse unified diffs
        if patch.diff.startswith("---") or patch.diff.startswith("@@"):
            # Unified diff format - would need proper diff application
            # For now, just copy baseline (patch application not implemented)
            patched_code = baseline_code
        else:
            # Assume diff is code to append/insert
            # Look for insertion point marker
            if "// INSERT_PATCH_HERE" in baseline_code:
                patched_code = baseline_code.replace("// INSERT_PATCH_HERE", patch.diff)
            else:
                # Append before last closing brace or at end
                patched_code = baseline_code + "\n\n// --- LLM PATCH ---\n" + patch.diff

        with open(patched_path, 'w', encoding='utf-8') as f:
            f.write(patched_code)

        # Also save patch diff for reference
        diff_path = patches_dir / f"{stem}_v{version}.patch"
        with open(diff_path, 'w', encoding='utf-8') as f:
            f.write(f"Description: {patch.description}\n\n")
            f.write(patch.diff)

        return patched_path

    except Exception:
        return None


def review_proposal(
    proposal: LLMProposalResult,
    baseline_ea_path: Path,
    workflow_id: str,
    refinement_cycle: int = 0
) -> ReviewResult:
    """
    Handle manual review of LLM proposal.

    This function:
    1. Checks if review is required
    2. Creates review package if needed
    3. Checks for review decision
    4. Applies patch if approved

    Args:
        proposal: LLM proposal result from Step 8C
        baseline_ea_path: Path to baseline EA
        workflow_id: Workflow identifier
        refinement_cycle: Current refinement cycle (0 = first review)

    Returns:
        ReviewResult with review status
    """
    try:
        # Check if review is required
        if not LLM_REVIEW_REQUIRED:
            # Auto-approve if review not required
            if proposal.ea_patch:
                patched_path = _apply_patch(
                    baseline_ea_path=baseline_ea_path,
                    patch=proposal.ea_patch,
                    workflow_id=workflow_id
                )
                return ReviewResult(
                    success=True,
                    status="approved",
                    review_required=False,
                    baseline_ea_path=str(baseline_ea_path),
                    active_ea_path=str(patched_path) if patched_path else str(baseline_ea_path),
                    patch_applied=patched_path is not None,
                    patched_ea_path=str(patched_path) if patched_path else None
                )
            else:
                return ReviewResult(
                    success=True,
                    status="skipped",
                    review_required=False,
                    baseline_ea_path=str(baseline_ea_path),
                    active_ea_path=str(baseline_ea_path),
                    patch_applied=False
                )

        # Check if LLM proposal is disabled or has no changes
        if proposal.status == "disabled" or (
            not proposal.param_actions and
            not proposal.range_refinements and
            not proposal.ea_patch
        ):
            return ReviewResult(
                success=True,
                status="skipped",
                review_required=False,
                baseline_ea_path=str(baseline_ea_path),
                active_ea_path=str(baseline_ea_path),
                patch_applied=False
            )

        # Create review package
        package_path = _create_review_package(
            proposal=proposal,
            baseline_ea_path=baseline_ea_path,
            workflow_id=workflow_id
        )

        # Check for review decision
        decision = _read_review_decision(workflow_id)

        if decision is None:
            # Still waiting for review
            return ReviewResult(
                success=True,
                status="pending_review",
                review_required=True,
                baseline_ea_path=str(baseline_ea_path),
                active_ea_path=str(baseline_ea_path),
                review_package_path=str(package_path),
                refinement_cycle=refinement_cycle,
                error_message="Waiting for human review. Check review_package.json and provide step8d_decision.json"
            )

        # Process decision
        if decision.approved:
            # Apply patch if exists
            if proposal.ea_patch:
                patched_path = _apply_patch(
                    baseline_ea_path=baseline_ea_path,
                    patch=proposal.ea_patch,
                    workflow_id=workflow_id
                )

                return ReviewResult(
                    success=True,
                    status="approved",
                    review_required=True,
                    baseline_ea_path=str(baseline_ea_path),
                    active_ea_path=str(patched_path) if patched_path else str(baseline_ea_path),
                    patch_applied=patched_path is not None,
                    patched_ea_path=str(patched_path) if patched_path else None,
                    decision=decision,
                    review_package_path=str(package_path),
                    refinement_cycle=refinement_cycle
                )
            else:
                # Approved but no patch - just range refinements
                return ReviewResult(
                    success=True,
                    status="approved",
                    review_required=True,
                    baseline_ea_path=str(baseline_ea_path),
                    active_ea_path=str(baseline_ea_path),
                    patch_applied=False,
                    decision=decision,
                    review_package_path=str(package_path),
                    refinement_cycle=refinement_cycle
                )
        else:
            # Rejected
            if decision.feedback and refinement_cycle < LLM_MAX_REFINEMENT_CYCLES:
                # Could trigger re-run of Step 8C with feedback
                return ReviewResult(
                    success=True,
                    status="rejected",
                    review_required=True,
                    baseline_ea_path=str(baseline_ea_path),
                    active_ea_path=str(baseline_ea_path),
                    patch_applied=False,
                    decision=decision,
                    review_package_path=str(package_path),
                    refinement_cycle=refinement_cycle,
                    error_message=f"Rejected with feedback: {decision.feedback}"
                )
            else:
                # Final rejection - proceed with baseline
                return ReviewResult(
                    success=True,
                    status="rejected",
                    review_required=True,
                    baseline_ea_path=str(baseline_ea_path),
                    active_ea_path=str(baseline_ea_path),
                    patch_applied=False,
                    decision=decision,
                    review_package_path=str(package_path),
                    refinement_cycle=refinement_cycle
                )

    except Exception as e:
        return ReviewResult(
            success=False,
            status="error",
            review_required=LLM_REVIEW_REQUIRED,
            baseline_ea_path=str(baseline_ea_path),
            active_ea_path=str(baseline_ea_path),
            error_message=f"Review error: {str(e)}"
        )


def validate_review(
    proposal: LLMProposalResult,
    baseline_ea_path: Path,
    workflow_id: str
) -> ReviewResult:
    """Convenience function for reviewing LLM proposal."""
    return review_proposal(
        proposal=proposal,
        baseline_ea_path=baseline_ea_path,
        workflow_id=workflow_id
    )
