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

    def test_analyze_parameters_with_valid_response(self):
        """Test analyze_parameters with valid response file"""
        # Write request first
        write_analysis_request(
            workflow_id=self.workflow_id,
            parameters=self.parameters,
            usage_map=self.usage_map,
            ea_source=self.ea_source,
            output_dir=self.temp_dir
        )

        # Create valid response
        response_path = os.path.join(self.temp_dir, self.workflow_id, "llm", "step4_response.json")
        valid_response = {
            'wide_validation_params': {
                'FastMAPeriod': 20,
                'SlowMAPeriod': 50
            },
            'optimization_ranges': [
                {
                    'name': 'FastMAPeriod',
                    'optimize': True,
                    'start': 10,
                    'step': 5,
                    'stop': 50,
                    'category': 'signal',
                    'rationale': 'Primary trend indicator'
                }
            ]
        }
        with open(response_path, 'w', encoding='utf-8') as f:
            json.dump(valid_response, f)

        # Analyze
        result = analyze_parameters(
            workflow_id=self.workflow_id,
            parameters=self.parameters,
            usage_map=self.usage_map,
            ea_source=self.ea_source,
            output_dir=self.temp_dir
        )

        self.assertEqual(result.status, "validated")
        self.assertTrue(result.passed_gate())
        self.assertEqual(result.wide_validation_params['FastMAPeriod'], 20)
        self.assertEqual(len(result.optimization_ranges), 1)

    def test_validate_schema_optimize_true_missing_fields(self):
        """Test schema validation when optimize=true but missing start/step/stop"""
        invalid_response = {
            'wide_validation_params': {'FastMAPeriod': 20},
            'optimization_ranges': [
                {
                    'name': 'FastMAPeriod',
                    'optimize': True
                    # Missing start, step, stop
                }
            ]
        }

        errors = validate_response_schema(invalid_response)
        self.assertGreater(len(errors), 0)
        self.assertTrue(any('start' in e for e in errors))
        self.assertTrue(any('step' in e for e in errors))
        self.assertTrue(any('stop' in e for e in errors))

    def test_validate_schema_optimize_false_missing_default(self):
        """Test schema validation when optimize=false but missing default"""
        invalid_response = {
            'wide_validation_params': {'FastMAPeriod': 20},
            'optimization_ranges': [
                {
                    'name': 'FastMAPeriod',
                    'optimize': False
                    # Missing default
                }
            ]
        }

        errors = validate_response_schema(invalid_response)
        self.assertGreater(len(errors), 0)
        self.assertTrue(any('default' in e for e in errors))

    def test_validate_schema_invalid_types(self):
        """Test schema validation with invalid field types"""
        invalid_response = {
            'wide_validation_params': "not a dict",  # Should be dict
            'optimization_ranges': [
                {
                    'name': 123,  # Should be string
                    'optimize': "true"  # Should be boolean
                }
            ]
        }

        errors = validate_response_schema(invalid_response)
        self.assertGreater(len(errors), 0)

    def test_validate_schema_optional_fields(self):
        """Test schema validation accepts optional fields"""
        valid_response = {
            'wide_validation_params': {'FastMAPeriod': 20},
            'optimization_ranges': [
                {
                    'name': 'FastMAPeriod',
                    'optimize': True,
                    'start': 10,
                    'step': 5,
                    'stop': 50,
                    'category': 'signal',
                    'rationale': 'Testing rationale'
                }
            ]
        }

        errors = validate_response_schema(valid_response)
        self.assertEqual(errors, [])

    def test_read_analysis_response_not_found(self):
        """Test read_analysis_response when file doesn't exist"""
        response = read_analysis_response(
            workflow_id="nonexistent",
            output_dir=self.temp_dir
        )
        self.assertIsNone(response)

    def test_read_analysis_response_valid(self):
        """Test read_analysis_response with valid file"""
        # Create response directory and file
        llm_dir = os.path.join(self.temp_dir, self.workflow_id, "llm")
        os.makedirs(llm_dir, exist_ok=True)
        response_path = os.path.join(llm_dir, "step4_response.json")

        test_data = {'wide_validation_params': {}, 'optimization_ranges': []}
        with open(response_path, 'w', encoding='utf-8') as f:
            json.dump(test_data, f)

        response = read_analysis_response(
            workflow_id=self.workflow_id,
            output_dir=self.temp_dir
        )

        self.assertIsNotNone(response)
        self.assertIn('wide_validation_params', response)

    def test_read_analysis_response_invalid_json(self):
        """Test read_analysis_response with malformed JSON"""
        # Create response directory and malformed file
        llm_dir = os.path.join(self.temp_dir, self.workflow_id, "llm")
        os.makedirs(llm_dir, exist_ok=True)
        response_path = os.path.join(llm_dir, "step4_response.json")

        with open(response_path, 'w', encoding='utf-8') as f:
            f.write("{ invalid json }")

        with self.assertRaises(ValueError):
            read_analysis_response(
                workflow_id=self.workflow_id,
                output_dir=self.temp_dir
            )

    def test_validate_analysis_no_response(self):
        """Test validate_analysis when response doesn't exist"""
        result = validate_analysis(
            workflow_id="nonexistent",
            output_dir=self.temp_dir
        )

        self.assertEqual(result.status, "error")
        self.assertIn("Response file not found", result.validation_errors)

    def test_validate_analysis_valid_response(self):
        """Test validate_analysis with valid response file"""
        # Create response file
        llm_dir = os.path.join(self.temp_dir, self.workflow_id, "llm")
        os.makedirs(llm_dir, exist_ok=True)
        response_path = os.path.join(llm_dir, "step4_response.json")

        valid_response = {
            'wide_validation_params': {'FastMAPeriod': 20},
            'optimization_ranges': [
                {
                    'name': 'FastMAPeriod',
                    'optimize': False,
                    'default': 20
                }
            ]
        }
        with open(response_path, 'w', encoding='utf-8') as f:
            json.dump(valid_response, f)

        result = validate_analysis(
            workflow_id=self.workflow_id,
            output_dir=self.temp_dir
        )

        self.assertEqual(result.status, "validated")
        self.assertTrue(result.passed_gate())

    def test_analysis_result_to_dict(self):
        """Test AnalysisResult serialization"""
        result = AnalysisResult(
            wide_validation_params={'FastMAPeriod': 20},
            optimization_ranges=[{'name': 'FastMAPeriod', 'optimize': False, 'default': 20}],
            request_path='/path/to/request.json',
            response_path='/path/to/response.json',
            status='validated',
            validation_errors=[]
        )

        data = result.to_dict()

        self.assertIn('wide_validation_params', data)
        self.assertIn('optimization_ranges', data)
        self.assertIn('gate_passed', data)
        self.assertTrue(data['gate_passed'])

    def test_analyze_parameters_with_invalid_response(self):
        """Test analyze_parameters with invalid response file"""
        # Write request first
        write_analysis_request(
            workflow_id=self.workflow_id,
            parameters=self.parameters,
            usage_map=self.usage_map,
            ea_source=self.ea_source,
            output_dir=self.temp_dir
        )

        # Create invalid response (missing optimization_ranges)
        response_path = os.path.join(self.temp_dir, self.workflow_id, "llm", "step4_response.json")
        invalid_response = {
            'wide_validation_params': {'FastMAPeriod': 20}
            # Missing optimization_ranges
        }
        with open(response_path, 'w', encoding='utf-8') as f:
            json.dump(invalid_response, f)

        # Analyze
        result = analyze_parameters(
            workflow_id=self.workflow_id,
            parameters=self.parameters,
            usage_map=self.usage_map,
            ea_source=self.ea_source,
            output_dir=self.temp_dir
        )

        self.assertEqual(result.status, "error")
        self.assertFalse(result.passed_gate())
        self.assertGreater(len(result.validation_errors), 0)


if __name__ == '__main__':
    unittest.main()
