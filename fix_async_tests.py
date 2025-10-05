#!/usr/bin/env python3
"""
Script to add @pytest.mark.asyncio decorators to async test functions
"""
import os
import re

def fix_async_tests_in_file(filepath):
    """Add @pytest.mark.asyncio decorators to async test functions in a file"""
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Pattern to match async test functions without the decorator
    pattern = r'(\n    )(async def test_[^(]+\([^)]*\):)'
    
    def replacement(match):
        indent = match.group(1)
        func_def = match.group(2)
        return f'{indent}@pytest.mark.asyncio{indent}{func_def}'
    
    # Only add decorator if it's not already there
    lines = content.split('\n')
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r'    async def test_', line):
            # Check if previous line already has the decorator
            if i > 0 and '@pytest.mark.asyncio' not in lines[i-1]:
                new_lines.append('    @pytest.mark.asyncio')
        new_lines.append(line)
        i += 1
    
    new_content = '\n'.join(new_lines)
    
    if new_content != content:
        with open(filepath, 'w') as f:
            f.write(new_content)
        print(f"Fixed async tests in {filepath}")
        return True
    return False

def main():
    """Fix all test files"""
    test_files = [
        'tests/test_features_builds.py',
        'tests/test_features_configurations.py', 
        'tests/test_features_changes.py',
        'tests/test_features_grid.py',
        'tests/test_quickbuild_client.py',
        'tests/test_server.py'
    ]
    
    fixed_count = 0
    for filepath in test_files:
        if os.path.exists(filepath):
            if fix_async_tests_in_file(filepath):
                fixed_count += 1
    
    print(f"Fixed {fixed_count} test files")

if __name__ == "__main__":
    main()