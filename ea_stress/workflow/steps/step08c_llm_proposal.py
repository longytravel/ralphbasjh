"""
Step 8C: LLM Improvement Proposal

Purpose: Use evidence from Stat Explorer to propose parameter refinements
and EA enhancements/additions.

Per PRD Section 3, Step 8C:
- Uses offline LLM flow (request/response JSON files)
- Every recommendation must cite evidence from stat_explorer.json or pass1_results
- If evidence is weak, return "no change" for that area
- New logic allowed but must be tied to observed patterns
- Session-based sizing changes require clear profit concentration signal
- LLM patches must NOT modify injected OnTester or safety guard code
"""

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any
import json


from ...config import (
    RUNS_DIR,
    LLM_IMPROVEMENT_ENABLED,
    LLM_REVIEW_REQUIRED,
    LLM_ALLOW_NEW_LOGIC,
    STAT_MIN_SESSION_PROFIT_SHARE
)


@dataclass
class ParamAction:
    """Action for a parameter."""
    name: str
    action: str  # narrow_range, fix, remove
    rationale: str
    evidence: List[str] = field(default_factory=list)


@dataclass
class RangeRefinement:
    """Refined optimization range for a parameter."""
    name: str
    start: float
    step: float
    stop: float
    reason: str = ""


@dataclass
class EAPatch:
    """EA code patch proposal."""
    description: str
    diff: str


@dataclass
class LLMProposalResult:
    """Result from LLM improvement proposal step."""
    success: bool
    status: str  # request_written, response_received, validated, error, disabled
    request_path: Optional[str] = None
    response_path: Optional[str] = None
    param_actions: List[ParamAction] = field(default_factory=list)
    range_refinements: List[RangeRefinement] = field(default_factory=list)
    ea_patch: Optional[EAPatch] = None
    expected_impact: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    review_required: bool = True
    error_message: Optional[str] = None

    def passed_gate(self) -> bool:
        """Check if step passed (validated or disabled)."""
        return self.status in ["validated", "disabled"]

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "success": self.success,
            "status": self.status,
            "request_path": self.request_path,
            "response_path": self.response_path,
            "param_actions": [asdict(a) for a in self.param_actions],
            "range_refinements": [asdict(r) for r in self.range_refinements],
            "ea_patch": asdict(self.ea_patch) if self.ea_patch else None,
            "expected_impact": self.expected_impact,
            "risks": self.risks,
            "review_required": self.review_required,
            "error_message": self.error_message
        }
        return result


def _validate_response_schema(response: dict) -> tuple[bool, str]:
    """
    Validate LLM response against PRD Section 6.7 schema.

    Returns:
        Tuple of (is_valid, error_message)
    """
    required_fields = ["param_actions", "range_refinements", "expected_impact", "risks", "review_required"]

    for field in required_fields:
        if field not in response:
            return False, f"Missing required field: {field}"

    # Validate param_actions
    if not isinstance(response["param_actions"], list):
        return False, "param_actions must be a list"

    for i, action in enumerate(response["param_actions"]):
        if not isinstance(action, dict):
            return False, f"param_actions[{i}] must be an object"
        for req in ["name", "action", "rationale", "evidence"]:
            if req not in action:
                return False, f"param_actions[{i}] missing required field: {req}"
        if not isinstance(action["evidence"], list):
            return False, f"param_actions[{i}].evidence must be a list"

    # Validate range_refinements
    if not isinstance(response["range_refinements"], list):
        return False, "range_refinements must be a list"

    for i, ref in enumerate(response["range_refinements"]):
        if not isinstance(ref, dict):
            return False, f"range_refinements[{i}] must be an object"
        for req in ["name", "start", "step", "stop"]:
            if req not in ref:
                return False, f"range_refinements[{i}] missing required field: {req}"
        # Validate numeric types
        for num_field in ["start", "step", "stop"]:
            if not isinstance(ref[num_field], (int, float)):
                return False, f"range_refinements[{i}].{num_field} must be a number"

    # Validate ea_patch (optional)
    if "ea_patch" in response and response["ea_patch"] is not None:
        patch = response["ea_patch"]
        if not isinstance(patch, dict):
            return False, "ea_patch must be an object or null"
        if "description" not in patch or "diff" not in patch:
            return False, "ea_patch requires 'description' and 'diff' fields"

    # Validate expected_impact and risks
    if not isinstance(response["expected_impact"], list):
        return False, "expected_impact must be a list"
    if not isinstance(response["risks"], list):
        return False, "risks must be a list"

    # Validate review_required
    if not isinstance(response["review_required"], bool):
        return False, "review_required must be a boolean"

    return True, ""


def write_proposal_request(
    stat_explorer_data: dict,
    pass1_results: List[dict],
    parameter_usage_map: Dict[str, List[str]],
    ea_source_code: str,
    workflow_id: str
) -> Path:
    """
    Write LLM proposal request JSON.

    Args:
        stat_explorer_data: Output from Step 8B
        pass1_results: Pass 1 optimization results
        parameter_usage_map: Parameter usage map from Step 3
        ea_source_code: EA source code (baseline)
        workflow_id: Workflow identifier

    Returns:
        Path to request file
    """
    llm_dir = Path(RUNS_DIR) / "analysis" / workflow_id / "llm"
    llm_dir.mkdir(parents=True, exist_ok=True)

    request_path = llm_dir / "step8c_request.json"

    request = {
        "step": "8C",
        "purpose": "Generate improvement proposals based on evidence from optimization results",
        "inputs": {
            "stat_explorer": stat_explorer_data,
            "pass1_results_summary": {
                "total_passes": len(pass1_results),
                "top_10_passes": pass1_results[:10] if pass1_results else []
            },
            "parameter_usage_map": parameter_usage_map,
            "ea_source_code": ea_source_code
        },
        "instructions": {
            "rules": [
                "Every recommendation MUST cite evidence from stat_explorer or pass1_results",
                "If evidence is weak, return empty lists for that area",
                "New logic is allowed but MUST be tied to observed patterns (e.g., session bias)",
                f"Session-based sizing changes require profit concentration >= {STAT_MIN_SESSION_PROFIT_SHARE}%",
                "Patches MUST NOT modify injected OnTester or safety guard code",
                "Look for EA_STRESS_ONTESTER_INJECTED and EA_STRESS_SAFETY_INJECTED markers"
            ],
            "allow_new_logic": LLM_ALLOW_NEW_LOGIC
        },
        "output_schema": {
            "type": "object",
            "required": ["param_actions", "range_refinements", "expected_impact", "risks", "review_required"],
            "properties": {
                "param_actions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name", "action", "rationale", "evidence"],
                        "properties": {
                            "name": {"type": "string"},
                            "action": {"type": "string", "enum": ["narrow_range", "fix", "remove"]},
                            "rationale": {"type": "string"},
                            "evidence": {"type": "array", "items": {"type": "string"}}
                        }
                    }
                },
                "range_refinements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name", "start", "step", "stop"],
                        "properties": {
                            "name": {"type": "string"},
                            "start": {"type": "number"},
                            "step": {"type": "number"},
                            "stop": {"type": "number"},
                            "reason": {"type": "string"}
                        }
                    }
                },
                "ea_patch": {
                    "type": ["object", "null"],
                    "properties": {
                        "description": {"type": "string"},
                        "diff": {"type": "string"}
                    }
                },
                "expected_impact": {"type": "array", "items": {"type": "string"}},
                "risks": {"type": "array", "items": {"type": "string"}},
                "review_required": {"type": "boolean"}
            }
        }
    }

    with open(request_path, 'w') as f:
        json.dump(request, f, indent=2)

    return request_path


def read_proposal_response(workflow_id: str) -> Optional[dict]:
    """
    Read LLM proposal response if it exists.

    Returns:
        Response dict or None if not found
    """
    response_path = Path(RUNS_DIR) / "analysis" / workflow_id / "llm" / "step8c_response.json"

    if not response_path.exists():
        return None

    try:
        with open(response_path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def generate_llm_proposal(
    stat_explorer_data: dict,
    pass1_results: List[dict],
    parameter_usage_map: Dict[str, List[str]],
    ea_source_code: str,
    workflow_id: str
) -> LLMProposalResult:
    """
    Generate LLM improvement proposal using offline flow.

    This function:
    1. Checks if LLM improvement is enabled
    2. Writes request JSON if not exists
    3. Checks for response JSON
    4. Validates response schema

    Args:
        stat_explorer_data: Output from Step 8B
        pass1_results: Pass 1 optimization results
        parameter_usage_map: Parameter usage map from Step 3
        ea_source_code: EA source code (baseline)
        workflow_id: Workflow identifier

    Returns:
        LLMProposalResult with proposal data or status
    """
    # Check if LLM improvement is disabled
    if not LLM_IMPROVEMENT_ENABLED:
        return LLMProposalResult(
            success=True,
            status="disabled",
            error_message="LLM improvement is disabled in configuration"
        )

    try:
        llm_dir = Path(RUNS_DIR) / "analysis" / workflow_id / "llm"
        request_path = llm_dir / "step8c_request.json"
        response_path = llm_dir / "step8c_response.json"

        # Write request if not exists
        if not request_path.exists():
            write_proposal_request(
                stat_explorer_data=stat_explorer_data,
                pass1_results=pass1_results,
                parameter_usage_map=parameter_usage_map,
                ea_source_code=ea_source_code,
                workflow_id=workflow_id
            )

            return LLMProposalResult(
                success=True,
                status="request_written",
                request_path=str(request_path),
                error_message="Waiting for external LLM to provide step8c_response.json"
            )

        # Check for response
        response = read_proposal_response(workflow_id)

        if response is None:
            return LLMProposalResult(
                success=True,
                status="request_written",
                request_path=str(request_path),
                error_message="Waiting for external LLM to provide step8c_response.json"
            )

        # Validate response schema
        is_valid, error_msg = _validate_response_schema(response)

        if not is_valid:
            return LLMProposalResult(
                success=False,
                status="error",
                request_path=str(request_path),
                response_path=str(response_path),
                error_message=f"Invalid response schema: {error_msg}"
            )

        # Parse response into dataclasses
        param_actions = [
            ParamAction(
                name=a["name"],
                action=a["action"],
                rationale=a["rationale"],
                evidence=a["evidence"]
            )
            for a in response["param_actions"]
        ]

        range_refinements = [
            RangeRefinement(
                name=r["name"],
                start=r["start"],
                step=r["step"],
                stop=r["stop"],
                reason=r.get("reason", "")
            )
            for r in response["range_refinements"]
        ]

        ea_patch = None
        if response.get("ea_patch"):
            ea_patch = EAPatch(
                description=response["ea_patch"]["description"],
                diff=response["ea_patch"]["diff"]
            )

        return LLMProposalResult(
            success=True,
            status="validated",
            request_path=str(request_path),
            response_path=str(response_path),
            param_actions=param_actions,
            range_refinements=range_refinements,
            ea_patch=ea_patch,
            expected_impact=response["expected_impact"],
            risks=response["risks"],
            review_required=response["review_required"]
        )

    except Exception as e:
        return LLMProposalResult(
            success=False,
            status="error",
            error_message=f"LLM proposal error: {str(e)}"
        )


def validate_llm_proposal(
    stat_explorer_data: dict,
    pass1_results: List[dict],
    parameter_usage_map: Dict[str, List[str]],
    ea_source_code: str,
    workflow_id: str
) -> LLMProposalResult:
    """Convenience function for generating LLM proposal."""
    return generate_llm_proposal(
        stat_explorer_data=stat_explorer_data,
        pass1_results=pass1_results,
        parameter_usage_map=parameter_usage_map,
        ea_source_code=ea_source_code,
        workflow_id=workflow_id
    )
