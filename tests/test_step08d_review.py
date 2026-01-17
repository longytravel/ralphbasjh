"""Tests for Step 8D: Manual Review and Apply Patch."""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from ea_stress.workflow.steps.step08d_review import (
    ReviewResult,
    ReviewDecision,
    review_proposal,
    validate_review,
    _create_review_package,
    _read_review_decision,
    _apply_patch
)
from ea_stress.workflow.steps.step08c_llm_proposal import (
    LLMProposalResult,
    ParamAction,
    RangeRefinement,
    EAPatch
)


@pytest.fixture
def sample_proposal():
    """Create sample LLM proposal for testing."""
    return LLMProposalResult(
        success=True,
        status="validated",
        param_actions=[
            ParamAction(name="MA", action="narrow_range", rationale="Test", evidence=["e1"])
        ],
        range_refinements=[
            RangeRefinement(name="MA", start=10, step=2, stop=30, reason="cluster")
        ],
        ea_patch=EAPatch(description="Add filter", diff="// new code here"),
        expected_impact=["Better results"],
        risks=["Lower diversity"],
        review_required=True
    )


@pytest.fixture
def sample_proposal_no_patch():
    """Create sample LLM proposal without EA patch."""
    return LLMProposalResult(
        success=True,
        status="validated",
        param_actions=[
            ParamAction(name="MA", action="fix", rationale="Test", evidence=["e1"])
        ],
        range_refinements=[],
        ea_patch=None,
        expected_impact=["Simpler"],
        risks=["None"],
        review_required=True
    )


class TestCreateReviewPackage:
    """Test review package creation."""

    def test_creates_package_file(self, sample_proposal):
        """Test review package is created correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('ea_stress.workflow.steps.step08d_review.RUNS_DIR', tmpdir):
                # Create dummy EA file
                ea_path = Path(tmpdir) / "TestEA.mq5"
                ea_path.write_text("// EA code")

                package_path = _create_review_package(
                    proposal=sample_proposal,
                    baseline_ea_path=ea_path,
                    workflow_id="test123"
                )

                assert package_path.exists()

                with open(package_path) as f:
                    package = json.load(f)

                assert package["workflow_id"] == "test123"
                assert "proposal" in package
                assert "instructions" in package
                assert package["proposal"]["ea_patch"]["description"] == "Add filter"


class TestReadReviewDecision:
    """Test review decision reading."""

    def test_read_approved_decision(self):
        """Test reading approved decision."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('ea_stress.workflow.steps.step08d_review.RUNS_DIR', tmpdir):
                # Create decision file
                decision_dir = Path(tmpdir) / "analysis" / "test123" / "patches"
                decision_dir.mkdir(parents=True)
                decision_path = decision_dir / "step8d_decision.json"

                with open(decision_path, 'w') as f:
                    json.dump({"approved": True, "notes": "Looks good"}, f)

                decision = _read_review_decision("test123")

                assert decision is not None
                assert decision.approved is True
                assert decision.reviewer_notes == "Looks good"

    def test_read_rejected_decision(self):
        """Test reading rejected decision with feedback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('ea_stress.workflow.steps.step08d_review.RUNS_DIR', tmpdir):
                decision_dir = Path(tmpdir) / "analysis" / "test123" / "patches"
                decision_dir.mkdir(parents=True)
                decision_path = decision_dir / "step8d_decision.json"

                with open(decision_path, 'w') as f:
                    json.dump({"approved": False, "feedback": "Too risky"}, f)

                decision = _read_review_decision("test123")

                assert decision is not None
                assert decision.approved is False
                assert decision.feedback == "Too risky"

    def test_read_nonexistent_decision(self):
        """Test reading nonexistent decision returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('ea_stress.workflow.steps.step08d_review.RUNS_DIR', tmpdir):
                decision = _read_review_decision("nonexistent")
                assert decision is None


class TestApplyPatch:
    """Test patch application."""

    def test_apply_patch_creates_new_file(self):
        """Test patch application creates new EA version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('ea_stress.workflow.steps.step08d_review.RUNS_DIR', tmpdir):
                # Create baseline EA
                ea_path = Path(tmpdir) / "TestEA.mq5"
                ea_path.write_text("// Original EA code\n// INSERT_PATCH_HERE\n// More code")

                patch = EAPatch(description="Test patch", diff="// Patched code")

                patched_path = _apply_patch(
                    baseline_ea_path=ea_path,
                    patch=patch,
                    workflow_id="test123",
                    version=2
                )

                assert patched_path is not None
                assert patched_path.exists()
                assert "_v2" in patched_path.name

                content = patched_path.read_text()
                assert "Patched code" in content

    def test_apply_patch_appends_when_no_marker(self):
        """Test patch appends when no insertion marker."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('ea_stress.workflow.steps.step08d_review.RUNS_DIR', tmpdir):
                ea_path = Path(tmpdir) / "TestEA.mq5"
                ea_path.write_text("// Original EA code")

                patch = EAPatch(description="Test patch", diff="// New function")

                patched_path = _apply_patch(
                    baseline_ea_path=ea_path,
                    patch=patch,
                    workflow_id="test123"
                )

                assert patched_path is not None
                content = patched_path.read_text()
                assert "LLM PATCH" in content
                assert "New function" in content


class TestReviewProposal:
    """Test main review function."""

    def test_skips_when_review_not_required(self, sample_proposal):
        """Test skips review when not required."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('ea_stress.workflow.steps.step08d_review.RUNS_DIR', tmpdir):
                with patch('ea_stress.workflow.steps.step08d_review.LLM_REVIEW_REQUIRED', False):
                    ea_path = Path(tmpdir) / "TestEA.mq5"
                    ea_path.write_text("// EA code")

                    result = review_proposal(
                        proposal=sample_proposal,
                        baseline_ea_path=ea_path,
                        workflow_id="test123"
                    )

                    assert result.success
                    assert result.status == "approved"
                    assert result.review_required is False
                    assert result.patch_applied is True
                    assert result.passed_gate()

    def test_skips_when_no_changes(self):
        """Test skips when proposal has no changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('ea_stress.workflow.steps.step08d_review.RUNS_DIR', tmpdir):
                with patch('ea_stress.workflow.steps.step08d_review.LLM_REVIEW_REQUIRED', True):
                    empty_proposal = LLMProposalResult(
                        success=True,
                        status="validated",
                        param_actions=[],
                        range_refinements=[],
                        ea_patch=None,
                        expected_impact=[],
                        risks=[],
                        review_required=False
                    )

                    ea_path = Path(tmpdir) / "TestEA.mq5"
                    ea_path.write_text("// EA code")

                    result = review_proposal(
                        proposal=empty_proposal,
                        baseline_ea_path=ea_path,
                        workflow_id="test123"
                    )

                    assert result.success
                    assert result.status == "skipped"
                    assert result.passed_gate()

    def test_pending_review_when_no_decision(self, sample_proposal):
        """Test returns pending when no decision file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('ea_stress.workflow.steps.step08d_review.RUNS_DIR', tmpdir):
                with patch('ea_stress.workflow.steps.step08d_review.LLM_REVIEW_REQUIRED', True):
                    ea_path = Path(tmpdir) / "TestEA.mq5"
                    ea_path.write_text("// EA code")

                    result = review_proposal(
                        proposal=sample_proposal,
                        baseline_ea_path=ea_path,
                        workflow_id="test123"
                    )

                    assert result.success
                    assert result.status == "pending_review"
                    assert not result.passed_gate()
                    assert result.review_package_path is not None

    def test_approved_with_patch(self, sample_proposal):
        """Test approved decision applies patch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('ea_stress.workflow.steps.step08d_review.RUNS_DIR', tmpdir):
                with patch('ea_stress.workflow.steps.step08d_review.LLM_REVIEW_REQUIRED', True):
                    # Create EA and review package first
                    ea_path = Path(tmpdir) / "TestEA.mq5"
                    ea_path.write_text("// EA code")

                    # Create decision file
                    decision_dir = Path(tmpdir) / "analysis" / "test123" / "patches"
                    decision_dir.mkdir(parents=True)

                    # Create review package (needed for decision check)
                    _create_review_package(sample_proposal, ea_path, "test123")

                    # Create approved decision
                    decision_path = decision_dir / "step8d_decision.json"
                    with open(decision_path, 'w') as f:
                        json.dump({"approved": True}, f)

                    result = review_proposal(
                        proposal=sample_proposal,
                        baseline_ea_path=ea_path,
                        workflow_id="test123"
                    )

                    assert result.success
                    assert result.status == "approved"
                    assert result.patch_applied is True
                    assert result.patched_ea_path is not None
                    assert result.passed_gate()

    def test_rejected_decision(self, sample_proposal):
        """Test rejected decision uses baseline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('ea_stress.workflow.steps.step08d_review.RUNS_DIR', tmpdir):
                with patch('ea_stress.workflow.steps.step08d_review.LLM_REVIEW_REQUIRED', True):
                    ea_path = Path(tmpdir) / "TestEA.mq5"
                    ea_path.write_text("// EA code")

                    # Create decision
                    decision_dir = Path(tmpdir) / "analysis" / "test123" / "patches"
                    decision_dir.mkdir(parents=True)
                    _create_review_package(sample_proposal, ea_path, "test123")

                    decision_path = decision_dir / "step8d_decision.json"
                    with open(decision_path, 'w') as f:
                        json.dump({"approved": False}, f)

                    result = review_proposal(
                        proposal=sample_proposal,
                        baseline_ea_path=ea_path,
                        workflow_id="test123"
                    )

                    assert result.success
                    assert result.status == "rejected"
                    assert result.patch_applied is False
                    assert result.active_ea_path == str(ea_path)
                    assert result.passed_gate()


class TestReviewResultSerialization:
    """Test result serialization."""

    def test_to_dict(self):
        """Test to_dict serialization."""
        result = ReviewResult(
            success=True,
            status="approved",
            review_required=True,
            baseline_ea_path="/path/to/base.mq5",
            active_ea_path="/path/to/patched.mq5",
            patch_applied=True,
            decision=ReviewDecision(approved=True, reviewer_notes="LGTM")
        )

        d = result.to_dict()

        assert d["success"] is True
        assert d["status"] == "approved"
        assert d["decision"]["approved"] is True
        assert d["decision"]["reviewer_notes"] == "LGTM"


class TestConvenienceFunction:
    """Test convenience function."""

    def test_validate_review(self, sample_proposal):
        """Test validate_review is alias for review_proposal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('ea_stress.workflow.steps.step08d_review.RUNS_DIR', tmpdir):
                with patch('ea_stress.workflow.steps.step08d_review.LLM_REVIEW_REQUIRED', False):
                    ea_path = Path(tmpdir) / "TestEA.mq5"
                    ea_path.write_text("// EA code")

                    result = validate_review(
                        proposal=sample_proposal,
                        baseline_ea_path=ea_path,
                        workflow_id="test123"
                    )

                    assert result.status == "approved"
