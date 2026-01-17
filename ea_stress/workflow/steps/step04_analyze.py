"""
Step 4: Analyze Parameters

Receives and validates parameter analysis from external process (offline LLM flow).

Per PRD Section 3, Step 4:
- System writes step4_request.json with parameter usage map
- External LLM produces step4_response.json
- Workflow validates response against JSON schema
- Returns wide_validation_params and optimization_ranges
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any, Optional


@dataclass
class AnalysisResult:
    """Result of Step 4: Parameter Analysis"""

    # Required outputs
    wide_validation_params: Dict[str, Any]
    optimization_ranges: List[Dict[str, Any]]

    # Metadata
    request_path: str
    response_path: str
    status: str  # "request_written", "response_received", "validated", "error"
    validation_errors: List[str] = field(default_factory=list)

    def passed_gate(self) -> bool:
        """Gate: status == "validated" """
        return self.status == "validated"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'wide_validation_params': self.wide_validation_params,
            'optimization_ranges': self.optimization_ranges,
            'request_path': self.request_path,
            'response_path': self.response_path,
            'status': self.status,
            'validation_errors': self.validation_errors,
            'gate_passed': self.passed_gate()
        }


def validate_response_schema(response: Dict[str, Any]) -> List[str]:
    """
    Validate response against schema from PRD Section 3, Step 4.

    Returns list of validation errors (empty if valid).
    """
    errors = []

    # Check required top-level fields
    if 'wide_validation_params' not in response:
        errors.append("Missing required field: wide_validation_params")
    if 'optimization_ranges' not in response:
        errors.append("Missing required field: optimization_ranges")

    if errors:
        return errors

    # Validate wide_validation_params
    wide_params = response['wide_validation_params']
    if not isinstance(wide_params, dict):
        errors.append("wide_validation_params must be an object/dict")
    else:
        for key, value in wide_params.items():
            if not isinstance(value, (str, int, float, bool)):
                errors.append(f"wide_validation_params['{key}'] must be string, number, or boolean")

    # Validate optimization_ranges
    opt_ranges = response['optimization_ranges']
    if not isinstance(opt_ranges, list):
        errors.append("optimization_ranges must be an array/list")
    else:
        for i, item in enumerate(opt_ranges):
            if not isinstance(item, dict):
                errors.append(f"optimization_ranges[{i}] must be an object/dict")
                continue

            # Required fields
            if 'name' not in item:
                errors.append(f"optimization_ranges[{i}] missing required field: name")
            elif not isinstance(item['name'], str):
                errors.append(f"optimization_ranges[{i}].name must be a string")

            if 'optimize' not in item:
                errors.append(f"optimization_ranges[{i}] missing required field: optimize")
            elif not isinstance(item['optimize'], bool):
                errors.append(f"optimization_ranges[{i}].optimize must be a boolean")

            # Conditional fields
            if item.get('optimize', False):
                # If optimize=True, must have start, step, stop
                for field_name in ['start', 'step', 'stop']:
                    if field_name not in item:
                        errors.append(f"optimization_ranges[{i}] with optimize=true missing: {field_name}")
                    elif not isinstance(item[field_name], (int, float)):
                        errors.append(f"optimization_ranges[{i}].{field_name} must be a number")
            else:
                # If optimize=False, must have default
                if 'default' not in item:
                    errors.append(f"optimization_ranges[{i}] with optimize=false missing: default")
                elif not isinstance(item['default'], (int, float)):
                    errors.append(f"optimization_ranges[{i}].default must be a number")

            # Optional fields type checking
            if 'category' in item and not isinstance(item['category'], str):
                errors.append(f"optimization_ranges[{i}].category must be a string")
            if 'rationale' in item and not isinstance(item['rationale'], str):
                errors.append(f"optimization_ranges[{i}].rationale must be a string")

    return errors


def write_analysis_request(
    workflow_id: str,
    parameters: List[Dict[str, Any]],
    usage_map: Dict[str, List[Dict[str, str]]],
    ea_source: str,
    output_dir: str = "runs/analysis"
) -> str:
    """
    Write step4_request.json for external LLM processing.

    Args:
        workflow_id: Workflow identifier
        parameters: List of parameter dicts from Step 3
        usage_map: Parameter usage map from Step 3
        ea_source: EA source code
        output_dir: Base directory for analysis outputs

    Returns:
        Path to written request file
    """
    # Create output directory
    llm_dir = Path(output_dir) / workflow_id / "llm"
    llm_dir.mkdir(parents=True, exist_ok=True)

    # Build request payload
    request = {
        'workflow_id': workflow_id,
        'parameters': parameters,
        'usage_map': usage_map,
        'ea_source': ea_source,
        'instructions': {
            'task': 'Analyze EA parameters and provide optimization configuration',
            'required_outputs': {
                'wide_validation_params': 'Dictionary with loose parameter values to maximize trade generation (Step 5)',
                'optimization_ranges': 'List of parameter ranges for genetic optimization (Step 6-7)'
            },
            'guidelines': [
                'Use parameter usage map to understand how each parameter affects EA behavior',
                'Avoid name-only heuristics; analyze actual code usage',
                'wide_validation_params: Set to loose values that encourage trading',
                'optimization_ranges: For numeric inputs, provide start/step/stop; for others, fix at default',
                'Do not optimize safety parameters (EAStressSafety_*)',
                'Mark sinput parameters as optimize=false',
                'Provide evidence-based rationale for optimization decisions'
            ]
        }
    }

    # Write request file
    request_path = llm_dir / "step4_request.json"
    with open(request_path, 'w', encoding='utf-8') as f:
        json.dump(request, f, indent=2, ensure_ascii=False)

    return str(request_path)


def read_analysis_response(
    workflow_id: str,
    output_dir: str = "runs/analysis"
) -> Optional[Dict[str, Any]]:
    """
    Read and parse step4_response.json from external LLM.

    Args:
        workflow_id: Workflow identifier
        output_dir: Base directory for analysis outputs

    Returns:
        Parsed response dict, or None if file not found
    """
    response_path = Path(output_dir) / workflow_id / "llm" / "step4_response.json"

    if not response_path.exists():
        return None

    try:
        with open(response_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        raise ValueError(f"Failed to parse response file: {e}")


def analyze_parameters(
    workflow_id: str,
    parameters: List[Dict[str, Any]],
    usage_map: Dict[str, List[Dict[str, str]]],
    ea_source: str,
    output_dir: str = "runs/analysis",
    wait_for_response: bool = False
) -> AnalysisResult:
    """
    Step 4: Analyze Parameters (offline LLM flow).

    Workflow:
    1. Write step4_request.json with parameters and usage map
    2. Check for step4_response.json from external LLM
    3. Validate response against schema
    4. Return wide_validation_params and optimization_ranges

    Args:
        workflow_id: Workflow identifier
        parameters: Parameter list from Step 3
        usage_map: Parameter usage map from Step 3
        ea_source: EA source code for LLM context
        output_dir: Base directory for analysis outputs
        wait_for_response: If False, return after writing request (default workflow behavior)

    Returns:
        AnalysisResult with validation status
    """
    try:
        # Write request file
        request_path = write_analysis_request(
            workflow_id=workflow_id,
            parameters=parameters,
            usage_map=usage_map,
            ea_source=ea_source,
            output_dir=output_dir
        )

        # Check for response file
        response = read_analysis_response(workflow_id=workflow_id, output_dir=output_dir)

        if response is None:
            # Response not yet available - workflow should pause
            return AnalysisResult(
                wide_validation_params={},
                optimization_ranges=[],
                request_path=request_path,
                response_path=str(Path(output_dir) / workflow_id / "llm" / "step4_response.json"),
                status="request_written"
            )

        # Validate response schema
        validation_errors = validate_response_schema(response)

        if validation_errors:
            return AnalysisResult(
                wide_validation_params={},
                optimization_ranges=[],
                request_path=request_path,
                response_path=str(Path(output_dir) / workflow_id / "llm" / "step4_response.json"),
                status="error",
                validation_errors=validation_errors
            )

        # Success
        return AnalysisResult(
            wide_validation_params=response['wide_validation_params'],
            optimization_ranges=response['optimization_ranges'],
            request_path=request_path,
            response_path=str(Path(output_dir) / workflow_id / "llm" / "step4_response.json"),
            status="validated"
        )

    except Exception as e:
        return AnalysisResult(
            wide_validation_params={},
            optimization_ranges=[],
            request_path="",
            response_path="",
            status="error",
            validation_errors=[str(e)]
        )


def validate_analysis(workflow_id: str, output_dir: str = "runs/analysis") -> AnalysisResult:
    """
    Convenience function to validate existing response file.

    Used when resuming workflow after external LLM has written response.
    """
    response = read_analysis_response(workflow_id=workflow_id, output_dir=output_dir)

    if response is None:
        return AnalysisResult(
            wide_validation_params={},
            optimization_ranges=[],
            request_path="",
            response_path=str(Path(output_dir) / workflow_id / "llm" / "step4_response.json"),
            status="error",
            validation_errors=["Response file not found"]
        )

    validation_errors = validate_response_schema(response)

    if validation_errors:
        return AnalysisResult(
            wide_validation_params={},
            optimization_ranges=[],
            request_path="",
            response_path=str(Path(output_dir) / workflow_id / "llm" / "step4_response.json"),
            status="error",
            validation_errors=validation_errors
        )

    return AnalysisResult(
        wide_validation_params=response['wide_validation_params'],
        optimization_ranges=response['optimization_ranges'],
        request_path=str(Path(output_dir) / workflow_id / "llm" / "step4_request.json"),
        response_path=str(Path(output_dir) / workflow_id / "llm" / "step4_response.json"),
        status="validated"
    )
