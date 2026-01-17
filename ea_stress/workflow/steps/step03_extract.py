"""
Step 3: Extract Parameters

Parses EA source code to extract all input parameters using regex pattern matching.
Implements multi-line joining, comment filtering, and type normalization per PRD Section 3.
"""

import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set
from pathlib import Path


# Type mappings per PRD Section 3
TYPE_MAPPINGS = {
    'int': 'int', 'uint': 'int', 'long': 'int', 'ulong': 'int',
    'short': 'int', 'ushort': 'int', 'char': 'int', 'uchar': 'int',
    'double': 'double', 'float': 'double',
    'bool': 'bool',
    'string': 'string',
    'datetime': 'datetime',
    'color': 'color',
}


@dataclass
class Parameter:
    """Represents a single input parameter from EA source code."""
    name: str
    type: str  # Original MQL5 type
    base_type: str  # Normalized type (int, double, bool, string, enum, datetime, color)
    default: Optional[str] = None
    comment: Optional[str] = None
    line: int = 0
    optimizable: bool = False  # True if: input (not sinput) AND numeric AND not EAStressSafety_*

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class ExtractResult:
    """Result of parameter extraction from EA source."""
    params_found: int
    optimizable_count: int
    parameters: List[Parameter] = field(default_factory=list)
    usage_map: Dict[str, List[str]] = field(default_factory=dict)  # param_name -> [usage locations]
    gate_passed: bool = False
    error: Optional[str] = None

    def passed_gate(self) -> bool:
        """Check if gate condition is met: params_found >= 1."""
        return self.params_found >= 1

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'params_found': self.params_found,
            'optimizable_count': self.optimizable_count,
            'parameters': [p.to_dict() for p in self.parameters],
            'usage_map': self.usage_map,
            'gate_passed': self.passed_gate(),
            'error': self.error
        }


def normalize_type(mql_type: str) -> str:
    """
    Normalize MQL5 type to base type.

    Per PRD Section 3:
    - int, uint, long, ulong, short, ushort, char, uchar -> int
    - double, float -> double
    - bool -> bool
    - string -> string
    - datetime -> datetime
    - color -> color
    - ENUM_* or UPPERCASE -> enum
    """
    mql_type_clean = mql_type.strip()

    # Check direct mappings
    if mql_type_clean in TYPE_MAPPINGS:
        return TYPE_MAPPINGS[mql_type_clean]

    # Check for enum types (ENUM_* or all uppercase)
    if mql_type_clean.startswith('ENUM_') or mql_type_clean.isupper():
        return 'enum'

    # Default to the original type if no mapping found
    return mql_type_clean


def is_numeric_type(base_type: str) -> bool:
    """Check if type is numeric (int or double)."""
    return base_type in ('int', 'double')


def remove_comments(content: str) -> tuple[str, Dict[int, bool]]:
    """
    Remove comments from source code and track which lines are comments.

    Returns:
        tuple: (cleaned_content, line_is_comment_dict)
        - cleaned_content: source with comments replaced by spaces
        - line_is_comment_dict: maps line number to whether it's in a comment
    """
    lines = content.split('\n')
    cleaned_lines = []
    line_is_comment = {}
    in_block_comment = False

    for i, line in enumerate(lines):
        line_num = i + 1
        cleaned = []
        j = 0
        is_comment_line = False

        while j < len(line):
            # Check for block comment start
            if not in_block_comment and j < len(line) - 1 and line[j:j+2] == '/*':
                in_block_comment = True
                cleaned.append(' ')
                cleaned.append(' ')
                j += 2
                is_comment_line = True
                continue

            # Check for block comment end
            if in_block_comment and j < len(line) - 1 and line[j:j+2] == '*/':
                in_block_comment = False
                cleaned.append(' ')
                cleaned.append(' ')
                j += 2
                continue

            # Check for line comment
            if not in_block_comment and j < len(line) - 1 and line[j:j+2] == '//':
                # Rest of line is comment
                cleaned.append(' ' * (len(line) - j))
                is_comment_line = True
                break

            # Regular character
            if in_block_comment:
                cleaned.append(' ')
                is_comment_line = True
            else:
                cleaned.append(line[j])
            j += 1

        cleaned_lines.append(''.join(cleaned))
        line_is_comment[line_num] = is_comment_line or in_block_comment

    return '\n'.join(cleaned_lines), line_is_comment


def remove_conditional_blocks(content: str) -> str:
    """
    Remove code inside #if 0 ... #endif blocks.

    Per PRD Section 3: Skip code inside `#if 0 ... #endif` blocks.
    """
    # Simple implementation: remove #if 0 ... #endif blocks
    pattern = r'#if\s+0\b.*?#endif'
    return re.sub(pattern, lambda m: ' ' * len(m.group(0)), content, flags=re.DOTALL)


def join_multiline_declarations(content: str) -> List[tuple[str, int]]:
    """
    Join multi-line declarations until semicolon.

    Returns list of (declaration_text, start_line_number) tuples.
    """
    lines = content.split('\n')
    declarations = []
    current_decl = []
    start_line = 0

    for i, line in enumerate(lines):
        line_num = i + 1
        stripped = line.strip()

        # Check if this looks like start of input declaration
        # Match 'input' or 'sinput' at start (with or without space after)
        if not current_decl and (stripped.startswith('input') or stripped.startswith('sinput')):
            # Make sure it's actually 'input' or 'sinput' keyword, not part of another word
            if (stripped.startswith('input ') or stripped.startswith('sinput ') or
                stripped == 'input' or stripped == 'sinput'):
                current_decl = [line]
                start_line = line_num
        elif current_decl:
            current_decl.append(line)

        # Check if we have a complete declaration (ends with semicolon)
        if current_decl and ';' in line:
            # Join the lines
            full_decl = ' '.join(current_decl)
            declarations.append((full_decl, start_line))
            current_decl = []
            start_line = 0

    return declarations


def parse_parameters(ea_path: str) -> List[Parameter]:
    """
    Parse input parameters from EA source code.

    Per PRD Section 3:
    - Pattern: ^\\s*(sinput|input)\\s+([\\w\\s]+?)\\s+(\\w+)\\s*(?:=\\s*([^;/]+?))?\\s*;(?:\\s*//\\s*(.*))?$
    - Join multi-line declarations until semicolon
    - Ignore commented-out declarations
    - Skip code inside #if 0 ... #endif blocks
    """
    ea_path_obj = Path(ea_path)

    if not ea_path_obj.exists():
        raise FileNotFoundError(f"EA file not found: {ea_path}")

    # Read source
    with open(ea_path_obj, 'r', encoding='utf-8', errors='ignore') as f:
        content_original = f.read()

    # Remove #if 0 blocks
    content = remove_conditional_blocks(content_original)

    # Remove comments (but track which lines are comments)
    content_clean, line_is_comment = remove_comments(content)

    # Join multi-line declarations (on cleaned content)
    declarations = join_multiline_declarations(content_clean)

    # Also join on original content for comment extraction
    declarations_original = join_multiline_declarations(content)

    # Regex pattern per PRD
    # Pattern: (sinput|input)\s+([\w\s]+?)\s+(\w+)\s*(?:=\s*([^;/]+?))?\s*;(?:\s*//\s*(.*))?
    # Note: We need to handle the declaration text which may have been joined and cleaned
    pattern = re.compile(
        r'(sinput|input)\s+([\w\s]+?)\s+(\w+)\s*(?:=\s*([^;/]+?))?\s*;'
    )

    parameters = []

    for (decl_text, line_num), (decl_orig, _) in zip(declarations, declarations_original):
        # Try to match pattern on cleaned text
        match = pattern.search(decl_text)
        if not match:
            continue

        input_keyword = match.group(1)  # 'input' or 'sinput'
        type_str = match.group(2).strip()
        name = match.group(3).strip()
        default_value = match.group(4).strip() if match.group(4) else None

        # Extract comment from original source (after //)
        comment = None
        if '//' in decl_orig:
            comment_part = decl_orig.split('//', 1)[1].strip()
            # Remove trailing characters after semicolon in comment
            if comment_part:
                comment = comment_part

        # Normalize type
        base_type = normalize_type(type_str)

        # Determine if optimizable
        # Per PRD: true if: `input` (not `sinput`) AND numeric type AND not `EAStressSafety_*`
        is_optimizable = (
            input_keyword == 'input' and
            is_numeric_type(base_type) and
            not name.startswith('EAStressSafety_')
        )

        param = Parameter(
            name=name,
            type=type_str,
            base_type=base_type,
            default=default_value,
            comment=comment,
            line=line_num,
            optimizable=is_optimizable
        )

        parameters.append(param)

    return parameters


def build_usage_map(ea_path: str, parameters: List[Parameter]) -> Dict[str, List[str]]:
    """
    Build parameter usage map showing where each parameter is referenced in the code.

    Returns dict mapping parameter name to list of usage context strings.
    Per PRD Section 3: "Parameter usage map (function names and code snippets where each input is referenced)"
    """
    ea_path_obj = Path(ea_path)

    with open(ea_path_obj, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    usage_map = {}

    for param in parameters:
        param_name = param.name
        usages = []

        # Search for parameter usage in source
        current_function = None
        for i, line in enumerate(lines):
            line_num = i + 1

            # Track current function context
            func_match = re.search(r'\b(?:void|int|double|bool|string)\s+(\w+)\s*\(', line)
            if func_match:
                current_function = func_match.group(1)

            # Check if parameter is used in this line (not in its declaration)
            if param_name in line and line_num != param.line:
                # Extract context (strip and limit length)
                context = line.strip()
                if len(context) > 100:
                    context = context[:97] + '...'

                if current_function:
                    usages.append(f"{current_function}:{line_num}: {context}")
                else:
                    usages.append(f"line {line_num}: {context}")

        usage_map[param_name] = usages

    return usage_map


def extract_parameters(ea_path: str) -> ExtractResult:
    """
    Extract all input parameters from EA source code.

    This is the main entry point for Step 3.

    Args:
        ea_path: Path to EA source file (.mq5 or .mq4)

    Returns:
        ExtractResult with parameters, counts, and usage map
    """
    try:
        # Parse parameters
        parameters = parse_parameters(ea_path)

        # Build usage map
        usage_map = build_usage_map(ea_path, parameters)

        # Count optimizable parameters
        optimizable_count = sum(1 for p in parameters if p.optimizable)

        # Create result
        result = ExtractResult(
            params_found=len(parameters),
            optimizable_count=optimizable_count,
            parameters=parameters,
            usage_map=usage_map,
            gate_passed=len(parameters) >= 1
        )

        return result

    except Exception as e:
        return ExtractResult(
            params_found=0,
            optimizable_count=0,
            parameters=[],
            usage_map={},
            gate_passed=False,
            error=str(e)
        )


def validate_extraction(ea_path: str) -> bool:
    """
    Convenience function to validate parameter extraction.

    Returns True if gate passes (params_found >= 1).
    """
    result = extract_parameters(ea_path)
    return result.passed_gate()
