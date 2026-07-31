"""
Structure and Design Helper Functions
Consolidates all UI structure, formatting, and template-related utilities.
"""
from pathlib import Path
from string import Template
from datetime import datetime
import pandas as pd

from runtime_paths import get_resource_dir

# Use resource dir so templates work when run as PyInstaller exe
BASE_DIR = get_resource_dir()
TEMPLATES_DIR = BASE_DIR / "templates"


# ===============================
# HTML/Template Helpers
# ===============================

def load_css(filename: str) -> str:
    """
    Load CSS from a file and wrap it in <style> tags.
    
    Args:
        filename: Name of the CSS file (e.g., 'styles.css')
    
    Returns:
        CSS wrapped in <style> tags
    """
    css_path = BASE_DIR / filename
    if not css_path.exists():
        raise FileNotFoundError(f"CSS file not found: {css_path}")
    
    with open(css_path, 'r', encoding='utf-8') as f:
        css_content = f.read()
    
    return f"<style>\n{css_content}\n</style>"


def load_js(filename: str) -> str:
    """
    Load JavaScript from a file and wrap it in <script> tags.
    
    Args:
        filename: Name of the JS file (e.g., 'scripts.js')
    
    Returns:
        JavaScript wrapped in <script> tags
    """
    js_path = BASE_DIR / filename
    if not js_path.exists():
        raise FileNotFoundError(f"JavaScript file not found: {js_path}")
    
    with open(js_path, 'r', encoding='utf-8') as f:
        js_content = f.read()
    
    return f"<script>\n{js_content}\n</script>"


def load_html_template(template_name: str, **kwargs) -> str:
    """
    Load an HTML template and substitute variables.
    
    Args:
        template_name: Name of the template file (e.g., 'executive_summary.html')
        **kwargs: Variables to substitute in the template using {variable} syntax
    
    Returns:
        HTML string with variables substituted
    """
    template_path = TEMPLATES_DIR / template_name
    if not template_path.exists():
        raise FileNotFoundError(f"Template file not found: {template_path}")
    
    with open(template_path, 'r', encoding='utf-8') as f:
        template_content = f.read()
    
    # Use Python's string format for substitution
    try:
        return template_content.format(**kwargs)
    except KeyError as e:
        # Extract the missing key name from the KeyError
        missing_key = e.args[0] if e.args else "unknown"
        provided_vars = ", ".join(sorted(kwargs.keys())) if kwargs else "none"
        raise ValueError(
            f"Missing template variable '{missing_key}' in template '{template_name}'. "
            f"Provided variables: [{provided_vars}]"
        )


def load_html_template_template(template_name: str, **kwargs) -> str:
    """
    Load an HTML template using Python's Template class (for $variable syntax).
    Useful for templates that use $variable syntax (like donut chart).
    
    Args:
        template_name: Name of the template file
        **kwargs: Variables to substitute using $variable syntax
    
    Returns:
        HTML string with variables substituted
    """
    template_path = TEMPLATES_DIR / template_name
    if not template_path.exists():
        raise FileNotFoundError(f"Template file not found: {template_path}")
    
    with open(template_path, 'r', encoding='utf-8') as f:
        template_content = f.read()
    
    template = Template(template_content)
    try:
        return template.substitute(**kwargs)
    except (KeyError, ValueError) as e:
        # Template.substitute raises KeyError for missing placeholders
        # Extract the missing key name from the exception
        missing_key = e.args[0] if e.args else "unknown"
        provided_vars = ", ".join(sorted(kwargs.keys())) if kwargs else "none"
        raise ValueError(
            f"Missing template variable '{missing_key}' in template '{template_name}'. "
            f"Provided variables: [{provided_vars}]"
        )


# ===============================
# Formatting Helpers
# ===============================

def html_escape(s: str) -> str:
    """
    Escape HTML special characters.
    
    Args:
        s: String to escape
    
    Returns:
        Escaped string
    """
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def safe_float(v, default: float = 0.0) -> float:
    """
    Safely convert a value to float, returning default if conversion fails.
    
    Args:
        v: Value to convert
        default: Default value if conversion fails
    
    Returns:
        Float value or default
    """
    try:
        f = float(v)
        if pd.isna(f):
            return default
        return f
    except Exception:
        return default


def fmt_minutes_ago(ts) -> str:
    """
    Format timestamp as "X min ago" or "1 min" if <= 1 minute.
    Safe for exe/startup when ts is None (returns "Never").
    
    Args:
        ts: Timestamp to format (datetime or None)
    
    Returns:
        Formatted string
    """
    if ts is None:
        return "Never"
    delta = datetime.now() - ts
    mins = max(0, int(delta.total_seconds() // 60))
    return "1 min" if mins <= 1 else f"{mins} min"


def trend(delta: float, unit: str = "") -> tuple[str, str]:
    """
    Format trend delta with arrow and CSS class.
    
    Args:
        delta: Change value (positive = up, negative = down)
        unit: Unit string to append (e.g., "%", "₹")
    
    Returns:
        Tuple of (formatted string, CSS class name)
    """
    if delta > 0:
        return f"▲ +{abs(delta):.0f}{unit}", "kpi-trend-up"
    if delta < 0:
        return f"▼ -{abs(delta):.0f}{unit}", "kpi-trend-down"
    return "—", "kpi-trend-flat"


def name_parts(full_name: str | None) -> tuple[str, str]:
    """
    Split full name into first and last name.
    
    Args:
        full_name: Full name string
    
    Returns:
        Tuple of (first_name, last_name)
    """
    if not full_name:
        return ("Patient", "")
    parts = str(full_name).strip().split()
    if len(parts) == 1:
        return (parts[0], "")
    return (parts[0], parts[-1])
