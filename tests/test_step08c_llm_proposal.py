"""Tests for Step 8C: LLM Improvement Proposal."""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from ea_stress.workflow.steps.step08c_llm_proposal import (
    LLMProposalResult,
    ParamAction,
    RangeRefinement,
    EAPatch,
    write_proposal_request,
    read_proposal_response,
    generate_llm_proposal,
    validate_llm_proposal,
    _validate_response_schema
)


class TestValidateResponseSchema:
    """Test response schema validation."""

    def test_valid_response(self):
        """Test valid response passes validation."""
        response = {
            "param_actions": [
                {
                    "name": "FastMA",
                    "action": "narrow_range",
                    "rationale": "Top decile clusters around 15-25",
                    "evidence": ["param_sensitivity.FastMA corr=0.42"]
                }
            ],
            "range_refinements": [
                {"name": "FastMA", "start": 15, "step": 2, "stop": 25}
            ],
            "expected_impact": ["Improve convergence"],
            "risks": ["May miss edge cases"],
            "review_required": True
        }
        is_valid, error = _validate_response_schema(response)
        assert is_valid
        assert error == ""

    def test_missing_required_field(self):
        """Test missing required field fails validation."""
        response = {
            "param_actions": [],
            "range_refinements": [],
            "expected_impact": [],
            # Missing: risks, review_required
        }
        is_valid, error = _validate_response_schema(response)
        assert not is_valid
        assert "Missing required field" in error

    def test_invalid_param_action(self):
        """Test invalid param_action structure fails."""
        response = {
            "param_actions": [{"name": "Test"}],  # Missing action, rationale, evidence
            "range_refinements": [],
            "expected_impact": [],
            "risks": [],
            "review_required": True
        }
        is_valid, error = _validate_response_schema(response)
        assert not is_valid
        assert "param_actions[0]" in error

    def test_invalid_range_refinement(self):
        """Test invalid range_refinement structure fails."""
        response = {
            "param_actions": [],
            "range_refinements": [{"name": "Test"}],  # Missing start, step, stop
            "expected_impact": [],
            "risks": [],
            "review_required": True
        }
        is_valid, error = _validate_response_schema(response)
        assert not is_valid
        assert "range_refinements[0]" in error

    def test_non_numeric_range_values(self):
        """Test non-numeric range values fail."""
        response = {
            "param_actions": [],
            "range_refinements": [
                {"name": "Test", "start": "10", "step": 2, "stop": 20}  # start is string
            ],
            "expected_impact": [],
            "risks": [],
            "review_required": True
        }
        is_valid, error = _validate_response_schema(response)
        assert not is_valid
        assert "must be a number" in error

    def test_valid_with_ea_patch(self):
        """Test valid response with EA patch."""
        response = {
            "param_actions": [],
            "range_refinements": [],
            "ea_patch": {
                "description": "Add session filter",
                "diff": "--- a/EA.mq5\n+++ b/EA.mq5\n..."
            },
            "expected_impact": ["Filter out low-profit sessions"],
            "risks": ["Reduced trade count"],
            "review_required": True
        }
        is_valid, error = _validate_response_schema(response)
        assert is_valid

    def test_invalid_ea_patch(self):
        """Test invalid EA patch structure fails."""
        response = {
            "param_actions": [],
            "range_refinements": [],
            "ea_patch": {"description": "Missing diff field"},
            "expected_impact": [],
            "risks": [],
            "review_required": True
        }
        is_valid, error = _validate_response_schema(response)
        assert not is_valid
        assert "ea_patch" in error


class TestWriteProposalRequest:
    """Test request file writing."""

    def test_write_request(self):
        """Test writing proposal request creates valid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('ea_stress.workflow.steps.step08c_llm_proposal.RUNS_DIR', tmpdir):
                request_path = write_proposal_request(
                    stat_explorer_data={"session_stats": {}},
                    pass1_results=[{"result": 100, "params": {"MA": 20}}],
                    parameter_usage_map={"MA": ["OnTick", "OnInit"]},
                    ea_source_code="// EA code here",
                    workflow_id="test123"
                )

                assert request_path.exists()

                with open(request_path) as f:
                    request = json.load(f)

                assert request["step"] == "8C"
                assert "stat_explorer" in request["inputs"]
                assert "output_schema" in request


class TestReadProposalResponse:
    """Test response file reading."""

    def test_read_existing_response(self):
        """Test reading existing response file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('ea_stress.workflow.steps.step08c_llm_proposal.RUNS_DIR', tmpdir):
                # Create response file
                response_dir = Path(tmpdir) / "analysis" / "test123" / "llm"
                response_dir.mkdir(parents=True)
                response_path = response_dir / "step8c_response.json"

                response_data = {
                    "param_actions": [],
                    "range_refinements": [],
                    "expected_impact": [],
                    "risks": [],
                    "review_required": False
                }

                with open(response_path, 'w') as f:
                    json.dump(response_data, f)

                result = read_proposal_response("test123")
                assert result is not None
                assert result["review_required"] is False

    def test_read_nonexistent_response(self):
        """Test reading nonexistent response returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('ea_stress.workflow.steps.step08c_llm_proposal.RUNS_DIR', tmpdir):
                result = read_proposal_response("nonexistent")
                assert result is None


class TestGenerateLLMProposal:
    """Test main proposal generation function."""

    def test_disabled_returns_disabled_status(self):
        """Test disabled LLM returns disabled status."""
        with patch('ea_stress.workflow.steps.step08c_llm_proposal.LLM_IMPROVEMENT_ENABLED', False):
            result = generate_llm_proposal(
                stat_explorer_data={},
                pass1_results=[],
                parameter_usage_map={},
                ea_source_code="",
                workflow_id="test"
            )

            assert result.success
            assert result.status == "disabled"
            assert result.passed_gate()

    def test_writes_request_when_none_exists(self):
        """Test writes request file when none exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('ea_stress.workflow.steps.step08c_llm_proposal.RUNS_DIR', tmpdir):
                with patch('ea_stress.workflow.steps.step08c_llm_proposal.LLM_IMPROVEMENT_ENABLED', True):
                    result = generate_llm_proposal(
                        stat_explorer_data={},
                        pass1_results=[],
                        parameter_usage_map={},
                        ea_source_code="// code",
                        workflow_id="test123"
                    )

                    assert result.success
                    assert result.status == "request_written"
                    assert result.request_path is not None
                    assert Path(result.request_path).exists()
                    assert not result.passed_gate()  # Still waiting for response

    def test_validates_response_when_exists(self):
        """Test validates response when it exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('ea_stress.workflow.steps.step08c_llm_proposal.RUNS_DIR', tmpdir):
                with patch('ea_stress.workflow.steps.step08c_llm_proposal.LLM_IMPROVEMENT_ENABLED', True):
                    # Create response file
                    response_dir = Path(tmpdir) / "analysis" / "test123" / "llm"
                    response_dir.mkdir(parents=True)

                    # First write request
                    request_path = response_dir / "step8c_request.json"
                    with open(request_path, 'w') as f:
                        json.dump({"step": "8C"}, f)

                    # Write valid response
                    response_path = response_dir / "step8c_response.json"
                    with open(response_path, 'w') as f:
                        json.dump({
                            "param_actions": [
                                {
                                    "name": "MA",
                                    "action": "narrow_range",
                                    "rationale": "Test",
                                    "evidence": ["test evidence"]
                                }
                            ],
                            "range_refinements": [
                                {"name": "MA", "start": 10, "step": 2, "stop": 30, "reason": "cluster"}
                            ],
                            "expected_impact": ["Better results"],
                            "risks": ["Lower diversity"],
                            "review_required": True
                        }, f)

                    result = generate_llm_proposal(
                        stat_explorer_data={},
                        pass1_results=[],
                        parameter_usage_map={},
                        ea_source_code="// code",
                        workflow_id="test123"
                    )

                    assert result.success
                    assert result.status == "validated"
                    assert result.passed_gate()
                    assert len(result.param_actions) == 1
                    assert result.param_actions[0].name == "MA"
                    assert len(result.range_refinements) == 1
                    assert result.review_required is True


class TestLLMProposalResultSerialization:
    """Test result serialization."""

    def test_to_dict(self):
        """Test to_dict serialization."""
        result = LLMProposalResult(
            success=True,
            status="validated",
            param_actions=[
                ParamAction(name="MA", action="fix", rationale="Test", evidence=["e1"])
            ],
            range_refinements=[
                RangeRefinement(name="MA", start=10, step=2, stop=30, reason="cluster")
            ],
            ea_patch=EAPatch(description="Test patch", diff="---\n+++"),
            expected_impact=["Better"],
            risks=["Risk"],
            review_required=True
        )

        d = result.to_dict()

        assert d["success"] is True
        assert d["status"] == "validated"
        assert len(d["param_actions"]) == 1
        assert d["param_actions"][0]["name"] == "MA"
        assert d["ea_patch"]["description"] == "Test patch"
        assert d["review_required"] is True


class TestConvenienceFunction:
    """Test convenience function."""

    def test_validate_llm_proposal(self):
        """Test validate_llm_proposal is alias for generate_llm_proposal."""
        with patch('ea_stress.workflow.steps.step08c_llm_proposal.LLM_IMPROVEMENT_ENABLED', False):
            result = validate_llm_proposal(
                stat_explorer_data={},
                pass1_results=[],
                parameter_usage_map={},
                ea_source_code="",
                workflow_id="test"
            )

            assert result.status == "disabled"
