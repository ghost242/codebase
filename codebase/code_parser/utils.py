import logging
import os
from typing import Optional


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def compute_package_full_path(source_file: str, project_root: str) -> str:
    """
    Computes the package full path from a source file relative to the project root.
    """
    rel_path = os.path.relpath(source_file, project_root)
    norm_path = os.path.normpath(rel_path)
    parts = norm_path.split(os.sep)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = os.path.splitext(parts[-1])[0]
    return ".".join(parts)


def find_package_source(module_name: str) -> Optional[str]:
    """
    Finds the source file for a given Python module by searching sys.path.
    """
    import sys

    for path in sys.path:
        module_path = os.path.join(path, *module_name.split("."))
        file_path = module_path + ".py"
        if os.path.isfile(file_path):
            return file_path
        if os.path.isdir(module_path):
            init_file = os.path.join(module_path, "__init__.py")
            if os.path.isfile(init_file):
                return init_file
    return None
