import json
import pathlib
import asyncio
import logging

logger = logging.getLogger(__name__)

async def load_json_async(file_path: pathlib.Path, default_return_type: type = dict) -> dict | list:
    """
    Asynchronously loads a JSON file.

    Args:
        file_path: The path to the JSON file.
        default_return_type: The type to return if the file doesn't exist or an error occurs 
                             (e.g., dict for profiles, list for lists of items).

    Returns:
        The loaded JSON data as a dictionary or list, or the default_return_type on error/not found.
    """
    if not await asyncio.to_thread(file_path.exists):
        logger.warning(f"File not found: {file_path}, returning default type: {default_return_type}")
        return default_return_type() if callable(default_return_type) else default_return_type
    try:
        content = await asyncio.to_thread(file_path.read_text, encoding='utf-8')
        return json.loads(content)
    except Exception as e:
        logger.error(f"Error reading or parsing JSON file {file_path}: {e}", exc_info=True)
        return default_return_type() if callable(default_return_type) else default_return_type

async def save_json_async(file_path: pathlib.Path, data: dict | list) -> bool:
    """
    Asynchronously saves data to a JSON file.

    Args:
        file_path: The path to the JSON file.
        data: The dictionary or list to save.

    Returns:
        True if saving was successful, False otherwise.
    """
    try:
        # Ensure parent directory exists
        await asyncio.to_thread(file_path.parent.mkdir, parents=True, exist_ok=True)
        json_string = json.dumps(data, indent=2)
        await asyncio.to_thread(file_path.write_text, json_string, encoding='utf-8')
        logger.debug(f"Successfully saved JSON to {file_path}")
        return True
    except Exception as e:
        logger.error(f"Error writing JSON file {file_path}: {e}", exc_info=True)
        return False

def get_nested_value(data_dict: dict, path: str, default=None):
    """
    Helper to safely get a value from a nested dictionary using a dot-separated path.
    
    Args:
        data_dict: The dictionary to search within.
        path: A string representing the path to the value (e.g., "basic_info.name").
        default: The value to return if the path is not found or an intermediate key is missing.
        
    Returns:
        The value at the specified path or the default value.
    """
    keys = path.split('.')
    val = data_dict
    for key in keys:
        if isinstance(val, dict) and key in val:
            val = val[key]
        else:
            return default
    return val