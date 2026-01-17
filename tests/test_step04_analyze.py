"""
Tests for Step 4: Parameter Analysis
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from ea_stress.workflow.steps.step04_analyze import (
    analyze_parameters,
    validate_analysis,
    validate_response_schema,
    write_analysis_request,
    read_analysis_response,
    AnalysisResult
)


class TestStep04Analyze(unittest.TestCase):
    """Test Step 4: Parameter Analysis"""

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
            },
            {
                'name': 'LotSize',
                'type': 'double',
                'base_type': 'double',
                'default': '0.1',
                'comment': 'Lot size',
                'line': 12,
                'optimizable': True
            },
            {
                'name': 'EnableFilter',
                'type': 'bool',
                'base_type': 'bool',
                'default': 'true',
                'comment': 'Enable filtering',
                'line': 13,
                'optimizable': False
            },
            {
                'name': 'MagicNumber',
                'type': 'int',
                'base_type': 'int',
                'default': '12345',
                'comment': 'Magic number',
                'line': 14,
                'optimizable': False
            }
        ]

        # Sample usage map
        self.usage_map = {
            'FastMAPeriod': [
                {'function': 'OnInit', 'snippet': 'fastHandle = iMA(_Symbol, PERIOD_CURRENT, FastMAPeriod, 0, MODE_SMA, PRICE_CLOSE);'}
            ],
            'SlowMAPeriod': [
                {'function': 'OnInit', 'snippet': 'slowHandle = iMA(_Symbol, PERIOD_CURRENT, SlowMAPeriod, 0, MODE_SMA, PRICE_CLOSE);'}
            ],
            'LotSize': [
                {'function': 'OpenTrade', 'snippet': 'trade.PositionOpen(_Symbol, ORDER_TYPE_BUY, LotSize, Ask, 0, 0);'}
            ]
        }

        self.ea_source = "// Sample EA code\ninput int FastMAPeriod = 20;\n"

    def tearDown(self):
        """Clean up"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_write_analysis_request(self):
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
            request = json.load(f)

        self.assertEqual(request['workflow_id'], self.workflow_id)
        self.assertEqual(len(request['parameters']), 5)
        self.assertIn('usage_map', request)
        self.assertIn('ea_source', request)
        self.assertIn('instructions', request)

    def test_read_analysis_response_not_found(self):
        """Test reading response when file doesn't exist"""
        response = read_analysis_response(
            workflow_id=self.workflow_id,
            output_dir=self.temp_dir
        )

        self.assertIsNone(response)

    def test_read_analysis_response_success(self):
        """Test reading valid response file"""
        # Create response file
        llm_dir = Path(self.temp_dir) / self.workflow_id / "llm"
        llm_dir.mkdir(parents=True, exist_ok=True)

        response_data = {
            'wide_validation_params': {
                'FastMAPeriod': 15,
                'SlowMAPeriod': 40,
                'LotSize': 0.1,
                'EnableFilter': False
            },
            'optimization_ranges': [
                {'name': 'FastMAPeriod', 'optimize': True, 'start': 10, 'step': 2, 'stop': 30},
                {'name': 'SlowMAPeriod', 'optimize': True, 'start': 30, 'step': 5, 'stop': 80}
            ]
        }

        response_path = llm_dir / "step4_response.json"
        with open(response_path, 'w', encoding='utf-8') as f:
            json.dump(response_data, f)

        # Read response
        response = read_analysis_response(
            workflow_id=self.workflow_id,
            output_dir=self.temp_dir
        )

        self.assertIsNotNone(response)
        self.assertIn('wide_validation_params', response)
        self.assertIn('optimization_ranges', response)

    def test_validate_response_schema_valid(self):
        """Test schema validation with valid response"""
        response = {
            'wide_validation_params': {
                'FastMAPeriod': 15,
                'LotSize': 0.1,
                'EnableFilter': True
            },
            'optimization_ranges': [
                {'name': 'FastMAPeriod', 'optimize': True, 'start': 10, 'step': 2, 'stop': 30},
                {'name': 'LotSize', 'optimize': False, 'default': 0.1}
            ]
        }

        errors = validate_response_schema(response)
        self.assertEqual(errors, [])

    def test_validate_response_schema_missing_fields(self):
        """Test schema validation with missing required fields"""
        response = {
            'wide_validation_params': {}
            # Missing optimization_ranges
        }

        errors = validate_response_schema(response)
        self.assertGreater(len(errors), 0)
        self.assertTrue(any('optimization_ranges' in e for e in errors))

    def test_validate_response_schema_invalid_types(self):
        """Test schema validation with invalid types"""
        response = {
            'wide_validation_params': "invalid",  # Should be dict
            'optimization_ranges': []
        }

        errors = validate_response_schema(response)
        self.assertGreater(len(errors), 0)
        self.assertTrue(any('must be an object' in e for e in errors))

    def test_validate_response_schema_optimize_true_missing_range(self):
        """Test schema validation: optimize=true requires start/step/stop"""
        response = {
            'wide_validation_params': {},
            'optimization_ranges': [
                {'name': 'FastMAPeriod', 'optimize': True}
                # Missing start, step, stop
            ]
        }

        errors = validate_response_schema(response)
        self.assertGreater(len(errors), 0)
        self.assertTrue(any('start' in e for e in errors))
        self.assertTrue(any('step' in e for e in errors))
        self.assertTrue(any('stop' in e for e in errors))

    def test_validate_response_schema_optimize_false_missing_default(self):
        """Test schema validation: optimize=false requires default"""
        response = {
            'wide_validation_params': {},
            'optimization_ranges': [
                {'name': 'MagicNumber', 'optimize': False}
                # Missing default
            ]
        }

        errors = validate_response_schema(response)
        self.assertGreater(len(errors), 0)
        self.assertTrue(any('default' in e for e in errors))

    def test_analyze_parameters_no_response(self):
        """Test analyze_parameters when response doesn't exist yet"""
        result = analyze_parameters(
            workflow_id=self.workflow_id,
            parameters=self.parameters,
            usage_map=self.usage_map,
            ea_source=self.ea_source,
            output_dir=self.temp_dir,
            wait_for_response=False
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

        # Write valid response
        llm_dir = Path(self.temp_dir) / self.workflow_id / "llm"
        response_data = {
            'wide_validation_params': {
                'FastMAPeriod': 15,
                'SlowMAPeriod': 40,
                'LotSize': 0.1,
                'EnableFilter': False,
                'MagicNumber': 12345
            },
            'optimization_ranges': [
                {'name': 'FastMAPeriod', 'optimize': True, 'start': 10, 'step': 2, 'stop': 30, 'category': 'signal'},
                {'name': 'SlowMAPeriod', 'optimize': True, 'start': 30, 'step': 5, 'stop': 80, 'category': 'signal'},
                {'name': 'LotSize', 'optimize': False, 'default': 0.1},
                {'name': 'MagicNumber', 'optimize': False, 'default': 12345}
            ]
        }

        response_path = llm_dir / "step4_response.json"
        with open(response_path, 'w', encoding='utf-8') as f:
            json.dump(response_data, f)

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
        self.assertEqual(len(result.wide_validation_params), 5)
        self.assertEqual(len(result.optimization_ranges), 4)
        self.assertEqual(result.validation_errors, [])

    def test_analyze_parameters_with_invalid_response(self):
        """Test analyze_parameters with invalid response"""
        # Write request
        write_analysis_request(
            workflow_id=self.workflow_id,
            parameters=self.parameters,
            usage_map=self.usage_map,
            ea_source=self.ea_source,
            output_dir=self.temp_dir
        )

        # Write invalid response
        llm_dir = Path(self.temp_dir) / self.workflow_id / "llm"
        response_data = {
            'wide_validation_params': {},
            'optimization_ranges': [
                {'name': 'FastMAPeriod', 'optimize': True}  # Missing start/step/stop
            ]
        }

        response_path = llm_dir / "step4_response.json"
        with open(response_path, 'w', encoding='utf-8') as f:
            json.dump(response_data, f)

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

    def test_validate_analysis_convenience_function(self):
        """Test validate_analysis convenience function"""
        # Create valid response
        llm_dir = Path(self.temp_dir) / self.workflow_id / "llm"
        llm_dir.mkdir(parents=True, exist_ok=True)

        response_data = {
            'wide_validation_params': {'FastMAPeriod': 20},
            'optimization_ranges': [
                {'name': 'FastMAPeriod', 'optimize': True, 'start': 10, 'step': 2, 'stop': 30}
            ]
        }

        response_path = llm_dir / "step4_response.json"
        with open(response_path, 'w', encoding='utf-8') as f:
            json.dump(response_data, f)

        # Validate
        result = validate_analysis(workflow_id=self.workflow_id, output_dir=self.temp_dir)

        self.assertEqual(result.status, "validated")
        self.assertTrue(result.passed_gate())

    def test_result_to_dict(self):
        """Test AnalysisResult.to_dict() serialization"""
        result = AnalysisResult(
            wide_validation_params={'FastMAPeriod': 20},
            optimization_ranges=[{'name': 'FastMAPeriod', 'optimize': True, 'start': 10, 'step': 2, 'stop': 30}],
            request_path="/path/to/request.json",
            response_path="/path/to/response.json",
            status="validated",
            validation_errors=[]
        )

        data = result.to_dict()

        self.assertIn('wide_validation_params', data)
        self.assertIn('optimization_ranges', data)
        self.assertIn('status', data)
        self.assertIn('gate_passed', data)
        self.assertTrue(data['gate_passed'])

    def test_optional_fields_in_optimization_ranges(self):
        """Test that optional fields (category, rationale) are accepted"""
        response = {
            'wide_validation_params': {},
            'optimization_ranges': [
                {
                    'name': 'FastMAPeriod',
                    'optimize': True,
                    'start': 10,
                    'step': 2,
                    'stop': 30,
                    'category': 'signal',
                    'rationale': 'Fast MA controls entry timing'
                }
            ]
        }

        errors = validate_response_schema(response)
        self.assertEqual(errors, [])


if __name__ == '__main__':
    unittest.main()
