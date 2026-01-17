import os
import csv
import io
from typing import Dict

def load_navigation_map(root_path: str) -> Dict[str, str]:
    """
    Reads navigation.js from the root_path and parses the CSV content.
    Returns a dictionary mapping section number (e.g., "2.1") to the absolute file path.
    """
    nav_path = os.path.join(root_path, "navigation.js")
    
    if not os.path.exists(nav_path):
        print(f"Warning: navigation.js not found at {nav_path}")
        return {}

    with open(nav_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Strip the javascript variable declaration
    prefix = "const NAVIGATION_DATA = `"
    if prefix in content:
        content = content.split(prefix)[1]
    
    content = content.strip()
    if content.endswith("`"):
        content = content[:-1]

    nav_map: Dict[str, str] = {}
    f_csv = io.StringIO(content.strip())
    reader = csv.DictReader(f_csv)
    
    for row in reader:
        section_num = row.get("number")
        filepath = row.get("filepath")
        if section_num and filepath and filepath.strip():
            abs_path = os.path.abspath(os.path.join(root_path, filepath.strip()))
            nav_map[section_num.strip()] = abs_path
            
    return nav_map
