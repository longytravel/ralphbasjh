"""
Data models for EA Stress Test System.

Defines the workflow state structure and serialization.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from enum import Enum


class WorkflowStatus(Enum):
    """Workflow execution status values."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class StepStatus(Enum):
    """Individual step execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepResult:
    """Result of a single workflow step execution."""
    step_id: str
    status: StepStatus
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'step_id': self.step_id,
            'status': self.status.value,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'error': self.error,
            'metadata': self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StepResult':
        """Create from dictionary."""
        return cls(
            step_id=data['step_id'],
            status=StepStatus(data['status']),
            started_at=data.get('started_at'),
            completed_at=data.get('completed_at'),
            error=data.get('error'),
            metadata=data.get('metadata', {})
        )


@dataclass
class OptimizationPass:
    """Tracks an optimization pass (Pass 1 or Pass 2)."""
    pass_number: int
    ini_file: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    results_file: Optional[str] = None
    top_passes: List[Dict[str, Any]] = field(default_factory=list)
    selected_for_backtest: List[int] = field(default_factory=list)


@dataclass
class WorkflowState:
    """
    Complete state of an EA stress test workflow.

    Persisted to JSON for checkpoint/resume capability.
    """
    # Identification
    workflow_id: str
    ea_name: str
    ea_path: str

    # Status
    status: WorkflowStatus
    current_step: Optional[str] = None

    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    # Configuration snapshot
    config_snapshot: Dict[str, Any] = field(default_factory=dict)

    # Step execution history
    steps: Dict[str, StepResult] = field(default_factory=dict)

    # Phase-specific data
    compiled_ex5_path: Optional[str] = None
    extracted_parameters: List[Dict[str, Any]] = field(default_factory=list)
    parameter_analysis: Dict[str, Any] = field(default_factory=dict)

    # Optimization tracking
    optimization_pass1: Optional[OptimizationPass] = None
    optimization_pass2: Optional[OptimizationPass] = None

    # Improvement cycle
    improvement_proposal: Optional[Dict[str, Any]] = None
    applied_patches: List[str] = field(default_factory=list)

    # Validation results
    backtest_results: List[Dict[str, Any]] = field(default_factory=list)
    monte_carlo_results: Optional[Dict[str, Any]] = None
    stress_test_results: Optional[Dict[str, Any]] = None
    forward_test_results: Optional[Dict[str, Any]] = None

    # Final scoring
    go_live_score: Optional[float] = None
    gate_results: Dict[str, bool] = field(default_factory=dict)

    # Multi-pair (for Step 14)
    symbol_pairs: List[str] = field(default_factory=list)

    # Error tracking
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data['status'] = self.status.value

        # Convert StepResult objects
        data['steps'] = {k: v.to_dict() for k, v in self.steps.items()}

        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkflowState':
        """Create from dictionary (deserialize from JSON)."""
        # Convert status enum
        data['status'] = WorkflowStatus(data['status'])

        # Convert step results
        if 'steps' in data:
            data['steps'] = {
                k: StepResult.from_dict(v)
                for k, v in data['steps'].items()
            }

        # Convert optimization passes
        if data.get('optimization_pass1'):
            data['optimization_pass1'] = OptimizationPass(**data['optimization_pass1'])
        if data.get('optimization_pass2'):
            data['optimization_pass2'] = OptimizationPass(**data['optimization_pass2'])

        return cls(**data)

    def save(self, path: Path) -> None:
        """Save state to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: Path) -> 'WorkflowState':
        """Load state from JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)

    def update_step(
        self,
        step_id: str,
        status: StepStatus,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Update or create a step result."""
        if step_id not in self.steps:
            self.steps[step_id] = StepResult(
                step_id=step_id,
                status=status
            )
        else:
            self.steps[step_id].status = status

        if status == StepStatus.RUNNING and not self.steps[step_id].started_at:
            self.steps[step_id].started_at = datetime.utcnow().isoformat()

        if status in (StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.SKIPPED):
            self.steps[step_id].completed_at = datetime.utcnow().isoformat()

        if error:
            self.steps[step_id].error = error

        if metadata:
            self.steps[step_id].metadata.update(metadata)

        self.current_step = step_id

    def get_step_status(self, step_id: str) -> StepStatus:
        """Get status of a specific step."""
        return self.steps.get(step_id, StepResult(step_id, StepStatus.PENDING)).status

    def add_error(self, error: str) -> None:
        """Add an error to the error log."""
        self.errors.append(f"[{datetime.utcnow().isoformat()}] {error}")

    def add_warning(self, warning: str) -> None:
        """Add a warning to the warning log."""
        self.warnings.append(f"[{datetime.utcnow().isoformat()}] {warning}")

    def is_step_completed(self, step_id: str) -> bool:
        """Check if a step has been completed."""
        return self.get_step_status(step_id) == StepStatus.COMPLETED

    def get_progress_summary(self) -> Dict[str, Any]:
        """Get a summary of workflow progress."""
        total_steps = len(self.steps)
        completed = sum(1 for s in self.steps.values() if s.status == StepStatus.COMPLETED)
        failed = sum(1 for s in self.steps.values() if s.status == StepStatus.FAILED)

        return {
            'workflow_id': self.workflow_id,
            'ea_name': self.ea_name,
            'status': self.status.value,
            'current_step': self.current_step,
            'progress': {
                'total_steps': total_steps,
                'completed': completed,
                'failed': failed,
                'percentage': (completed / total_steps * 100) if total_steps > 0 else 0
            },
            'timestamps': {
                'created_at': self.created_at,
                'started_at': self.started_at,
                'completed_at': self.completed_at
            },
            'errors': len(self.errors),
            'warnings': len(self.warnings)
        }

    def transition_to(self, new_status: WorkflowStatus) -> bool:
        """
        Transition workflow to a new status with validation.

        Returns True if transition is valid and executed, False otherwise.

        Valid transitions:
        - PENDING -> RUNNING
        - RUNNING -> COMPLETED, FAILED, PAUSED
        - PAUSED -> RUNNING, FAILED
        - FAILED -> RUNNING (retry)
        - COMPLETED -> (terminal state, no transitions)
        """
        valid_transitions = {
            WorkflowStatus.PENDING: {WorkflowStatus.RUNNING},
            WorkflowStatus.RUNNING: {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.PAUSED},
            WorkflowStatus.PAUSED: {WorkflowStatus.RUNNING, WorkflowStatus.FAILED},
            WorkflowStatus.FAILED: {WorkflowStatus.RUNNING},  # Allow retry
            WorkflowStatus.COMPLETED: set()  # Terminal state
        }

        if new_status not in valid_transitions.get(self.status, set()):
            self.add_warning(
                f"Invalid state transition: {self.status.value} -> {new_status.value}"
            )
            return False

        old_status = self.status
        self.status = new_status

        # Update timestamps based on transition
        if new_status == WorkflowStatus.RUNNING and not self.started_at:
            self.started_at = datetime.utcnow().isoformat()

        if new_status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED):
            self.completed_at = datetime.utcnow().isoformat()

        return True

    def start(self) -> bool:
        """Start the workflow (PENDING -> RUNNING)."""
        return self.transition_to(WorkflowStatus.RUNNING)

    def pause(self) -> bool:
        """Pause the workflow (RUNNING -> PAUSED)."""
        return self.transition_to(WorkflowStatus.PAUSED)

    def resume(self) -> bool:
        """Resume the workflow (PAUSED -> RUNNING)."""
        return self.transition_to(WorkflowStatus.RUNNING)

    def complete(self) -> bool:
        """Mark workflow as completed (RUNNING -> COMPLETED)."""
        return self.transition_to(WorkflowStatus.COMPLETED)

    def fail(self, error: Optional[str] = None) -> bool:
        """Mark workflow as failed (RUNNING/PAUSED -> FAILED)."""
        if error:
            self.add_error(error)
        return self.transition_to(WorkflowStatus.FAILED)

    def retry(self) -> bool:
        """Retry a failed workflow (FAILED -> RUNNING)."""
        return self.transition_to(WorkflowStatus.RUNNING)
