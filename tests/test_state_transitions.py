"""Test state transitions for WorkflowState."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ea_stress.models import WorkflowState, WorkflowStatus, StepStatus

# Use ASCII-compatible checkmark
CHECK = "[OK]"


def test_valid_transitions():
    """Test valid state transitions."""
    print("Testing valid state transitions...")

    # Create a workflow in PENDING state
    state = WorkflowState(
        workflow_id="test-001",
        ea_name="TestEA",
        ea_path="/path/to/test.mq5",
        status=WorkflowStatus.PENDING
    )

    assert state.status == WorkflowStatus.PENDING
    print("[OK] Initial state: PENDING")

    # PENDING -> RUNNING
    assert state.start() == True
    assert state.status == WorkflowStatus.RUNNING
    assert state.started_at is not None
    print("[OK] PENDING -> RUNNING (via start())")

    # RUNNING -> PAUSED
    assert state.pause() == True
    assert state.status == WorkflowStatus.PAUSED
    print("[OK] RUNNING -> PAUSED (via pause())")

    # PAUSED -> RUNNING
    assert state.resume() == True
    assert state.status == WorkflowStatus.RUNNING
    print("[OK] PAUSED -> RUNNING (via resume())")

    # RUNNING -> COMPLETED
    assert state.complete() == True
    assert state.status == WorkflowStatus.COMPLETED
    assert state.completed_at is not None
    print("[OK] RUNNING -> COMPLETED (via complete())")

    print("\nAll valid transitions passed!")


def test_invalid_transitions():
    """Test invalid state transitions are rejected."""
    print("\nTesting invalid state transitions...")

    # Try to complete from PENDING (should fail)
    state = WorkflowState(
        workflow_id="test-002",
        ea_name="TestEA",
        ea_path="/path/to/test.mq5",
        status=WorkflowStatus.PENDING
    )

    result = state.transition_to(WorkflowStatus.COMPLETED)
    assert result == False
    assert state.status == WorkflowStatus.PENDING
    assert len(state.warnings) > 0
    print("[OK] PENDING -> COMPLETED rejected")

    # Try to transition from COMPLETED (terminal state)
    state2 = WorkflowState(
        workflow_id="test-003",
        ea_name="TestEA",
        ea_path="/path/to/test.mq5",
        status=WorkflowStatus.COMPLETED
    )

    result = state2.transition_to(WorkflowStatus.RUNNING)
    assert result == False
    assert state2.status == WorkflowStatus.COMPLETED
    print("[OK] COMPLETED -> RUNNING rejected (terminal state)")

    print("\nAll invalid transitions properly rejected!")


def test_failure_and_retry():
    """Test failure state and retry logic."""
    print("\nTesting failure and retry...")

    state = WorkflowState(
        workflow_id="test-004",
        ea_name="TestEA",
        ea_path="/path/to/test.mq5",
        status=WorkflowStatus.PENDING
    )

    state.start()
    assert state.status == WorkflowStatus.RUNNING
    print("[OK] Started workflow")

    # Fail with error message
    assert state.fail("Test error occurred") == True
    assert state.status == WorkflowStatus.FAILED
    assert len(state.errors) > 0
    assert state.completed_at is not None
    print("[OK] RUNNING -> FAILED (via fail())")

    # Retry from failed state
    assert state.retry() == True
    assert state.status == WorkflowStatus.RUNNING
    print("[OK] FAILED -> RUNNING (via retry())")

    print("\nFailure and retry logic works correctly!")


def test_step_transitions():
    """Test step-level status updates."""
    print("\nTesting step-level transitions...")

    state = WorkflowState(
        workflow_id="test-005",
        ea_name="TestEA",
        ea_path="/path/to/test.mq5",
        status=WorkflowStatus.PENDING
    )

    # Update step to running
    state.update_step("step01", StepStatus.RUNNING)
    assert state.get_step_status("step01") == StepStatus.RUNNING
    assert state.steps["step01"].started_at is not None
    print("[OK] Step marked as RUNNING")

    # Complete step
    state.update_step("step01", StepStatus.COMPLETED, metadata={"result": "success"})
    assert state.get_step_status("step01") == StepStatus.COMPLETED
    assert state.steps["step01"].completed_at is not None
    assert state.is_step_completed("step01") == True
    print("[OK] Step marked as COMPLETED")

    # Fail a step
    state.update_step("step02", StepStatus.FAILED, error="Step failed")
    assert state.get_step_status("step02") == StepStatus.FAILED
    assert state.steps["step02"].error == "Step failed"
    print("[OK] Step marked as FAILED with error")

    print("\nStep-level transitions work correctly!")


def test_persistence_with_transitions():
    """Test that state transitions persist correctly."""
    print("\nTesting persistence with state transitions...")

    import tempfile

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_path = Path(f.name)

    try:
        # Create and transition workflow
        state = WorkflowState(
            workflow_id="test-006",
            ea_name="TestEA",
            ea_path="/path/to/test.mq5",
            status=WorkflowStatus.PENDING
        )

        state.start()
        state.update_step("step01", StepStatus.COMPLETED)
        state.pause()

        # Save state
        state.save(temp_path)
        print("[OK] Saved workflow state")

        # Load and verify
        loaded = WorkflowState.load(temp_path)
        assert loaded.status == WorkflowStatus.PAUSED
        assert loaded.started_at is not None
        assert loaded.is_step_completed("step01") == True
        print("[OK] Loaded workflow state with correct status and steps")

    finally:
        temp_path.unlink(missing_ok=True)

    print("\nPersistence with transitions works correctly!")


if __name__ == "__main__":
    test_valid_transitions()
    test_invalid_transitions()
    test_failure_and_retry()
    test_step_transitions()
    test_persistence_with_transitions()

    print("\n" + "="*50)
    print("All state transition tests passed! [OK]")
    print("="*50)
