"""
Tests for Step 4: Parameter Analysis

Per PRD Section 3, Step 4:
- Offline LLM flow with request/response JSON files
- Schema validation for response
- wide_validation_params and optimization_ranges output
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from ea_stress.workflow.steps.step04_analyze import (
    analyze_parameters,
    validate_analysis,
    validate_response_schema,
    write_analysis_request,
    read_analysis_response,
    AnalysisResult
)


class TestStep04Analyze(unittest.TestCase):
    """Test suite for Step 4: Parameter Analysis"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.workflow_id = "test_workflow_123"

        # Sample parameters from Step 3
        self.parameters = [
            {
                'name': 'FastMAPeriod',
                'type': 'int',
                'base_type': 'int',
                'default': '20',
                'comment': 'Fast MA period',
                'line': 10,
                'optimizable': True
            },
            {
                'name': 'SlowMAPeriod',
                'type': 'int',
                'base_type': 'int',
                'default': '50',
                'comment': 'Slow MA period',
                'line': 11,
                'optimizable': True
            }
        ]

        # Sample usage map from Step 3
        self.usage_map = {
            'FastMAPeriod': [
                {'function': 'OnInit', 'snippet': 'iMA(_Symbol, PERIOD_CURRENT, FastMAPeriod, ...)'}
            ]
        }

        self.ea_source = "// Sample EA source\ninput int FastMAPeriod = 20;\n"

    def tearDown(self):
        """Clean up test files"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_write_request_file(self):
        """Test writing step4_request.json"""
        request_path = write_analysis_request(
            workflow_id=self.workflow_id,
            parameters=self.parameters,
            usage_map=self.usage_map,
            ea_source=self.ea_source,
            output_dir=self.temp_dir
        )

        self.assertTrue(os.path.exists(request_path))

        # Verify content
        with open(request_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.assertEqual(data['workflow_id'], self.workflow_id)
        self.assertIn('instructions', data)

    def test_validate_schema_valid_response(self):
        """Test schema validation with valid response"""
        valid_response = {
            'wide_validation_params': {
                'FastMAPeriod': 20
            },
            'optimization_ranges': [
                {
                    'name': 'FastMAPeriod',
                    'optimize': True,
                    'start': 10,
                    'step': 5,
                    'stop': 50
                }
            ]
        }

        errors = validate_response_schema(valid_response)
        self.assertEqual(errors, [])

    def test_validate_schema_missing_required_field(self):
        """Test schema validation with missing required field"""
        invalid_response = {
            'wide_validation_params': {'FastMAPeriod': 20}
        }

        errors = validate_response_schema(invalid_response)
        self.assertGreater(len(errors), 0)
        self.assertTrue(any('optimization_ranges' in e for e in errors))

    def test_analyze_parameters_no_response(self):
        """Test analyze_parameters when response file doesn't exist (workflow pause)"""
        result = analyze_parameters(
            workflow_id=self.workflow_id,
            parameters=self.parameters,
            usage_map=self.usage_map,
            ea_source=self.ea_source,
            output_dir=self.temp_dir
        )

        self.assertIsInstance(result, AnalysisResult)
        self.assertEqual(result.status, "request_written")
        self.assertFalse(result.passed_gate())
        self.assertTrue(os.path.exists(result.request_path))


if __name__ == '__main__':
    unittest.main()
