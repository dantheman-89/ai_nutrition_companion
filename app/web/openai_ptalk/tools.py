import json
import pathlib
from datetime import datetime, timedelta
import copy
import asyncio
import logging
from .util import load_json_async, save_json_async, get_nested_value

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart # Keep for potential HTML/plain text later
from email.mime.text import MIMEText
from config import SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, DEFAULT_ORGANIZER_EMAIL

logger = logging.getLogger(__name__)

# File paths
USER_PROFILE_FILENAME = "user_profile.json"
VITALITY_DATA_FILENAME = "vitality_data.json"
HEALTHY_SWAP_FILENAME = "healthy_swap.json"
MEAL_PHOTOS_NUTRITION_FILENAME  = "meal_photos_nutrition.json"
TAKEAWAY_NUTRITION_FILENAME = "takeaway_nutrition.json"

# ─────────────────────────────────────────────────────────────────────────────
# Tool Functions - LLM definition + function implementation
# ─────────────────────────────────────────────────────────────────────────────

###### Helper function ######
def calculate_bmi(height_cm: float, weight_kg: float) -> float | None:
    """
    Calculate BMI using the formula: weight (kg) / (height (m))^2
    
    Args:
        height_cm: Height in centimeters
        weight_kg: Weight in kilograms
        
    Returns:
        BMI value rounded to 1 decimal place
    """
    if height_cm <= 0 or weight_kg <= 0:
        return None
    
    # Convert height from cm to m
    height_m = height_cm / 100
    
    # Calculate BMI
    bmi = weight_kg / (height_m ** 2)
    
    # Round to 1 decimal place
    return round(bmi, 1)

def check_goal_calculation_readiness(profile_data: dict) -> dict:
    """
    Checks if the profile contains all information required to calculate nutrition targets
    and updates the ready_to_calculate_goal flag.
    
    Required fields:
    - weight_kg
    - target_weight_kg
    - goal_timeframe_weeks
    - height_cm
    - age_years
    - sex
    
    Args:
        profile_data: The user profile data dictionary
        
    Returns:
        Updated profile data with ready_to_calculate_goal set appropriately
    """
    if "goals" not in profile_data:
        profile_data["goals"] = {}
    
    # Check for all required fields
    has_weight = profile_data.get("basic_info", {}).get("weight_kg") is not None
    has_target_weight = profile_data.get("goals", {}).get("weight_goals", {}).get("target_weight_kg") is not None
    has_timeframe = profile_data.get("goals", {}).get("weight_goals", {}).get("goal_timeframe_weeks") is not None
    has_height = profile_data.get("basic_info", {}).get("height_cm") is not None
    has_age = profile_data.get("basic_info", {}).get("age_years") is not None
    has_sex = profile_data.get("basic_info", {}).get("sex") is not None
    
    # All fields must be present to calculate goals
    ready_to_calculate = all([
        has_weight, has_target_weight, has_timeframe,
        has_height, has_age, has_sex
    ])
    
    profile_data["goals"]["ready_to_calculate_goal"] = ready_to_calculate
    print(f"Profile readiness for goal calculation: {ready_to_calculate}")
    
    return profile_data

################################################
###### Profile update tool ######
################################################

PROFILE_TOOL_DEFINITION = {
    "type": "function",
    "name": "update_user_profile",
    "description": "record height, weight, target weight, culture, food preferences, allergies, or eating habits",
    "parameters": {
        "type": "object",
        "properties": {
            "height":        {"type": "number", "description": "User height in cm"},
            "weight":        {"type": "number", "description": "User weight in kg"},
            "target_weight_kg": {"type": "number", "description": "Goal weight in kg"},
            "goal_timeframe_weeks": {"type": "number", "description": "Number of weeks to reach target weight"},
            "culture":       {"type": "string"},
            "food_preferences": {
            "type": "array",
            "items": {"type": "string"},
            "description": "E.g. ['vegetarian', 'lactose-free']"
            },
            "allergies": {
            "type": "array",
            "items": {"type": "string"}
            },
            "eating_habits": {
            "type": "array",
            "items": {"type": "string"},
            "description":"E.g. ['breakfast-skipper','late dinner']"
            }
        },
        "required": [], # Make all fields optional for partial updates
        "additionalProperties": False
    }
}

async def update_profile_json(user_data_dir, fields_to_update: dict):
    """
    Reads, updates, and writes the user profile JSON file.
    Maps flat fields from LLM to the appropriate nested structure in the user profile.
    
    Args:
        user_data_dir: Path to the user profile JSON file
        fields_to_update: Dictionary of fields to update from LLM
    
    Returns:
        JSON string containing the updated user profile
    """
    # Define mapping from flat LLM fields to nested JSON structure
    field_mapping = {
        "height": "basic_info.height_cm",
        "weight": "basic_info.weight_kg",
        "target_weight_kg": "goals.weight_goals.target_weight_kg",
        "goal_timeframe_weeks": "goals.weight_goals.goal_timeframe_weeks",
        "culture": "dietary_preferences.culture",
        "food_preferences": "dietary_preferences.food_preferences",
        "allergies": "dietary_preferences.allergies",
        "eating_habits": "eating_habits.eating_habits"
    }
    
    user_profile_path = user_data_dir / USER_PROFILE_FILENAME
    profile_data = {}
    try:
        # Load existing profile if it exists
        profile_data = await load_json_async(user_profile_path, default_return_type=dict)
        
        # Process each field using the mapping
        for field, value in fields_to_update.items():
            if field in field_mapping:
                # Get the nested path for this field
                path = field_mapping[field].split('.')
                
                # Navigate to the correct nested location
                current = profile_data
                for i, key in enumerate(path[:-1]):
                    # Create nested dictionaries if they don't exist
                    if key not in current:
                        current[key] = {}
                    current = current[key]
                
                # Set the value at the final level
                current[path[-1]] = value
            else:
                # For unmapped fields, place at top level (fallback)
                profile_data[field] = value

        # Calculate BMI if both height and weight are available
        if "height" in fields_to_update or "weight" in fields_to_update:
            if "basic_info" not in profile_data:
                profile_data["basic_info"] = {}
            # safely get current height and weight
            basic_info_data = profile_data.get("basic_info", {})
            current_height_cm = basic_info_data.get("height_cm")
            current_weight_kg = basic_info_data.get("weight_kg")
            if current_height_cm is not None and current_weight_kg is not None:
                profile_data["basic_info"]["bmi_kg_m2"] = calculate_bmi(current_height_cm, current_weight_kg)

        # Check if we have all required fields to calculate nutrition targets
        profile_data = check_goal_calculation_readiness(profile_data)

        # Write back to the file
        await save_json_async(user_profile_path, profile_data)
        print(f"Updated profile with fields: {', '.join(fields_to_update.keys())}")
        
    except Exception as e:
        print(f"Error updating profile JSON: {e}")
    
    # Return the updated profile as a JSON string
    return json.dumps(profile_data)
        
################################################        
###### Load External Health Data ######
################################################

LOAD_VITALITY_DATA_TOOL_DEFINITION = { # Explicitly type hint
    "type": "function",
    "name": "load_vitality_data",
    "description": "Loads and summarizes the user's available Vitality health data after getting permission. Provides a baseline understanding of activity and health status.",
    "parameters": {
        "type": "object",
        "properties": {}, # No parameters needed for this mock version
        "required": []
    }
}

async def load_vitality_data(user_data_dir: pathlib.Path) -> str:
    """
    Loads external health data (e.g., Vitality) for the user from a JSON file,
    updates the user profile with this data (extracting key metrics),
    and returns the original vitality data as a JSON string for the LLM or an error message.
    
    Args:
        user_data_dir: Path to the user data directory containing vitality_data.json and user_profile.json
        
    Returns:
        JSON string containing the full user profile for LLM use
    """
    vitality_data_path = user_data_dir / VITALITY_DATA_FILENAME
    user_profile_path = user_data_dir / USER_PROFILE_FILENAME
    system_message_for_llm = None  # additional system message for LLM if needed
    
    print(f"Executing load_vitality_data tool. Attempting to read: {vitality_data_path}")
    
    try:
        # 1. Read Vitality data
        vitality_data = await load_json_async(vitality_data_path, default_return_type=dict)
        
        # 2. Load existing user profile
        profile_data = await load_json_async(user_profile_path, default_return_type=dict)
        if not profile_data:
            logger.warning(f"User profile {user_profile_path} not found or empty. Starting fresh.")
            profile_data = {}
        
        # 3. Extract and map basic information
        basic_info = vitality_data.get("basic", {})
        if isinstance(basic_info, dict):
            if "basic_info" not in profile_data:
                profile_data["basic_info"] = {}
                
            # Map preferred_name if available
            if "preferred_name" in basic_info:
                profile_data["basic_info"]["preferred_name"] = basic_info["preferred_name"]
                
            # Map age_years if available
            if "age_years" in basic_info:
                profile_data["basic_info"]["age_years"] = basic_info["age_years"]
                
            # Map sex if available
            if "sex" in basic_info:
                profile_data["basic_info"]["sex"] = basic_info["sex"]
        
        # 4. Extract and map vitality status and points
        if "status" in vitality_data:
            if "vitality_information" not in profile_data:
                profile_data["vitality_information"] = {}
            profile_data["vitality_information"]["status"] = vitality_data["status"]
        
        if "points" in vitality_data:
            if "vitality_information" not in profile_data:
                profile_data["vitality_information"] = {}
            profile_data["vitality_information"]["points"] = vitality_data["points"]
        
        if "recent_activities" in vitality_data:
            if "vitality_information" not in profile_data:
                profile_data["vitality_information"] = {}
            profile_data["vitality_information"]["recent_activities"] = vitality_data["recent_activities"]
        
        # 5. Map health check data
        health_checks = vitality_data.get("health_checks", {})
        if isinstance(health_checks, dict):
            # Ensure vitality_information and health_checks exist
            if "vitality_information" not in profile_data:
                profile_data["vitality_information"] = {}
            if "health_checks" not in profile_data["vitality_information"]:
                profile_data["vitality_information"]["health_checks"] = {}
                
            # Map each health check field
            for key, value in health_checks.items():
                profile_data["vitality_information"]["health_checks"][key] = value
            
            # Map important metrics to basic_info section of the user profile
            height = health_checks.get("height")
            weight = health_checks.get("weight")
            last_check_date_str = health_checks.get("last_vitality_health_check")
            
            if height is not None:
                if "basic_info" not in profile_data:
                    profile_data["basic_info"] = {}
                profile_data["basic_info"]["height_cm"] = height
            
            if weight is not None:
                if "basic_info" not in profile_data:
                    profile_data["basic_info"] = {}
                profile_data["basic_info"]["weight_kg"] = weight
            
            # Calculate BMI if both height and weight are available
            if height is not None and weight is not None:
                if "basic_info" not in profile_data:
                    profile_data["basic_info"] = {}
                profile_data["basic_info"]["bmi_kg_m2"] = calculate_bmi(height, weight)

             # Check if weight/height data is stale
            if last_check_date_str and (weight is not None or height is not None):
                try:
                    # Assuming date format is YYYY-MM-DD
                    last_check_date = datetime.strptime(last_check_date_str, "%Y-%m-%d")
                    six_months_ago = datetime.now() - timedelta(days=6*30) # Approximate 6 months
                    if last_check_date < six_months_ago:
                        system_message_for_llm = "Your weight data from Vitality is more than 6 months out of date. Please tell the user about this and ask for their latest weight."
                        print("Vitality weight/height data is more than 6 months old.")
                except ValueError:
                    print(f"Could not parse last_vitality_health_check date: {last_check_date_str}")
        
        # 6. Check if we have all required fields to calculate nutrition targets
        profile_data = check_goal_calculation_readiness(profile_data)
        
        # 7. Write updated profile back
        await save_json_async(user_profile_path, profile_data)
        logger.info(f"Successfully updated {user_profile_path} with data from {vitality_data_path}") # Changed print to logger
        
        # 8. Return the full profile data as a JSON string for LLM use
        profile_data_for_llm = copy.deepcopy(profile_data)
        if system_message_for_llm: # Only add if it was set
            profile_data_for_llm['system_message_for_llm'] = system_message_for_llm
        return json.dumps(profile_data_for_llm, indent=2)
        
    except Exception as e:
        error_msg = f"Error processing file {vitality_data_path} or updating profile {user_profile_path}: {e}"
        print(error_msg)

################################################    
###### Load Healthy Swap Data ######
################################################

LOAD_HEALTHY_SWAP_TOOL_DEFINITION = {
    "type": "function",
    "name": "load_healthy_swap",
    "description": "Loads the user's healthy food swap recommendations and history from their profile. Provides information about NBA (Next Best Action) recommendations and previously suggested healthy alternatives.",
    "parameters": {
        "type": "object",
        "properties": {}, # No parameters needed for this version
        "required": []
    }
}

async def load_healthy_swap(user_data_dir: pathlib.Path) -> str:
    """
    Loads healthy food swap data for the user from the dedicated healthy_swap.json file
    and updates the user_profile.json with this data.
    
    Args:
        user_data_dir: Path to the user data directory containing healthy_swap.json
        
    Returns:
        JSON string containing the healthy swaps data
    """
    healthy_swap_path = user_data_dir / HEALTHY_SWAP_FILENAME
    user_profile_path = user_data_dir / USER_PROFILE_FILENAME
    
    print(f"Executing load_healthy_swap tool. Attempting to read: {healthy_swap_path}")
    
    try:
        # Load from dedicated healthy_swap.json file
        if healthy_swap_path.exists():
           # load the healthy swap data
            healthy_swaps_data = await load_json_async(healthy_swap_path, default_return_type=dict)
                
            # Update user profile with this data
            profile_data = await load_json_async(user_profile_path, default_return_type=dict)
            profile_data["healthy_swaps"] = healthy_swaps_data
            await save_json_async(user_profile_path, profile_data) # Write updated profile back
            logger.info(f"Updated user profile with healthy swaps data") # Changed print to logger

        else:
            logger.info(f"Dedicated healthy_swap.json not found or empty at {healthy_swap_path}") # Changed print to logger
            healthy_swaps_data = { # Ensure healthy_swaps_data is a dict for the return
                "NBA": None,
                "date_recommended": None,
                "recommended_swaps": None,
                "notes": None
            }

         # Return the healthy swaps data as a JSON string
        return json.dumps(healthy_swaps_data, indent=2)

    except Exception as e:
            error_msg = f"Error loading healthy swaps data: {e}"
            print(error_msg)
            return json.dumps({"status": "error", "message": error_msg})
       
################################################
###### Calculate Nutrition Targets ######
################################################

CALCULATE_TARGETS_TOOL_DEFINITION = {
    "type": "function",
    "name": "calculate_daily_nutrition_targets",
    "description": "Calculates baseline daily kilojoule and macronutrient targets based on user profile. EXCLUDES exercise energy expenditure - add Vitality exercise data separately to this baseline.",   
    "parameters": {
        "type": "object",
        "properties": {}, # No parameters needed, reads profile internally
        "required": []
    }
}

async def calculate_daily_nutrition_targets(user_data_dir: pathlib.Path) -> str:
    """
    Calculates estimated daily kilojoule budget and macronutrient targets based on the user's profile.
    Reads user profile, computes BMR, applies a baseline activity factor, calculates weight loss/gain deficit,
    and determines protein, fat, carbohydrate and fiber targets.
    
    Calculation steps:
    1. Calculate BMR using Mifflin-St Jeor equation
    2. Apply baseline activity factor (1.2 for lightly active)
    3. Calculate daily deficit based on weight goals and timeframe
    4. Determine macronutrient distribution
    
    Args:
        user_data_dir: Path to the user profile JSON file
        
    Returns:
        JSON string containing nutrition targets or error message
    """
    user_profile_path = user_data_dir / USER_PROFILE_FILENAME
    
    try:
        # 1. Load user profile
        profile_data = await load_json_async(user_profile_path, default_return_type=dict)
        if not profile_data:
            return json.dumps({"error": "User profile not found or empty"})
        
        # 2. Extract required fields from nested structure
        weight_kg = profile_data.get("basic_info", {}).get("weight_kg")
        target_weight_kg = profile_data.get("goals", {}).get("weight_goals", {}).get("target_weight_kg")
        goal_timeframe_weeks = profile_data.get("goals", {}).get("weight_goals", {}).get("goal_timeframe_weeks")
        height_cm = profile_data.get("basic_info", {}).get("height_cm")
        age_years = profile_data.get("basic_info", {}).get("age_years")
        sex = profile_data.get("basic_info", {}).get("sex")
        
        # 3. Validate all required fields are present
        required_fields = {
            "weight_kg": weight_kg,
            "target_weight_kg": target_weight_kg,
            "goal_timeframe_weeks": goal_timeframe_weeks,
            "height_cm": height_cm,
            "age_years": age_years,
            "sex": sex
        }
        
        missing_fields = [name for name, value in required_fields.items() if value is None]
        
        if missing_fields:
            return json.dumps({
                "error": f"Missing required profile fields: {', '.join(missing_fields)}"
            })
        
        # 4. Calculate BMR using Mifflin-St Jeor equation
        # BMR formula: (10 × weight in kg) + (6.25 × height in cm) - (5 × age in years) + s
        # where s is +5 for males and -161 for females
        sex_factor = 5 if sex.lower() == "male" else -161
        bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age_years) + sex_factor
        
        # 5. Apply baseline activity factor (1.2 for lightly active)
        # This represents basic daily activities excluding specific exercise
        baseline_activity_factor = 1.2
        tdee_kcal = bmr * baseline_activity_factor
        
        # 6. Calculate daily caloric adjustment for weight change
        # 7700 kcal ≈ energy in 1kg of body fat
        weight_difference = weight_kg - target_weight_kg
        daily_deficit_kcal = (weight_difference * 7700) / (7 * goal_timeframe_weeks)
        
        # 7. Adjust daily calories (subtract deficit for weight loss, add for gain)
        adjusted_kcal = tdee_kcal - daily_deficit_kcal
        
        # Ensure minimum healthy calorie intake (1200 kcal for women, 1500 for men)
        min_kcal = 1500 if sex.lower() == "male" else 1200
        if adjusted_kcal < min_kcal:
            adjusted_kcal = min_kcal
        
        # 8. Convert to kilojoules (1 kcal = 4.184 kJ)
        daily_kj = round(adjusted_kcal * 4.184)
        
        # 9. Calculate macronutrients
        # Protein: 1.6g per kg of body weight
        protein_g = round(1.6 * weight_kg)
        
        # Fat: 25% of total calories (9 kcal per gram)
        fat_g = round((0.25 * adjusted_kcal) / 9)
        
        # Protein and fat calories
        protein_kcal = protein_g * 4  # 4 kcal per gram of protein
        fat_kcal = fat_g * 9  # 9 kcal per gram of fat
        
        # Remaining calories for carbohydrates (4 kcal per gram)
        carbs_g = round((adjusted_kcal - protein_kcal - fat_kcal) / 4)
        
        # Ensure carbs don't go negative (adjust fat if needed)
        if carbs_g < 0:
            carbs_g = 50  # Minimum healthy carbs
            # Recalculate fat based on remaining calories
            remaining_kcal = adjusted_kcal - (protein_g * 4) - (carbs_g * 4)
            fat_g = round(remaining_kcal / 9)
        
        # Fiber: 14g per 1000 kcal
        fiber_g = round(adjusted_kcal / 1000 * 14)
        
        # 10. Prepare targets
        nutrition_targets = {
            "daily_kilojoules": daily_kj,
            "protein_grams": protein_g,
            "fat_grams": fat_g,
            "carbohydrate_grams": carbs_g,
            "fiber_grams": fiber_g
        }
        
        # 11. Update the user profile with these targets
        if "goals" not in profile_data:
            profile_data["goals"] = {}
        if "nutritional_goals" not in profile_data["goals"]:
            profile_data["goals"]["nutritional_goals"] = {}
            
        profile_data["goals"]["nutritional_goals"] = nutrition_targets
        profile_data["goals"]["goal_set"] = True
        
        # 12. Write updated profile back to file
        await save_json_async(user_profile_path, profile_data)
        
        # 13. Return the nutrition targets as a JSON string
        return json.dumps(nutrition_targets, indent=2)
        
    except Exception as e:
        error_msg = f"Error calculating nutrition targets: {str(e)}"
        print(error_msg)


################################################
# Meal_logger_tool - System triggered
################################################
NUTRITION_LOGGER_TOOL_DEFINITION = {
    "type": "function",
    "name": "nutrition_logger_tool",
    "description": "An internal tool that logs nutritional contents of user uploaded meal photos and provides a summary. This tool will be triggered on the client side. do not use it directly",
    "parameters": { 
        "type": "object",
        "properties": {}, # No parameters needed, reads profile internally
        "required": []
    }
}

async def log_meal_photos_from_filenames(user_data_dir: pathlib.Path, photo_filenames: list[str]) -> dict:
    """
    Processes meal photo filenames, updates user profile with nutrition info,
    and returns a summary for AI and the updated profile.
    """
    logger.info(f"Tool: log_meal_photos_from_filenames called with {photo_filenames}") # Changed print to logger
    await asyncio.sleep(4) # Simulate processing delay

    profile_path = user_data_dir / USER_PROFILE_FILENAME
    meal_photos_path = pathlib.Path(__file__).parent / "data" / "nutrition" / MEAL_PHOTOS_NUTRITION_FILENAME

    profile_data = await load_json_async(profile_path, default_return_type=dict)
    all_meal_photo_data = await load_json_async(meal_photos_path, default_return_type=list)

    if not isinstance(profile_data, dict) or not isinstance(all_meal_photo_data, list):
        return {
            "summary_for_ai": "Error: Could not load necessary data files.",
            "updated_full_profile": profile_data if isinstance(profile_data, dict) else {}
        }

    logged_meals_details = []
    total_consumed_today = {
        "kilojoules": 0, "protein_grams": 0, "fat_grams": 0,
        "carbohydrate_grams": 0, "fiber_grams": 0
    }

    for filename_to_match in photo_filenames:
        matched_meal = None
        for meal_entry in all_meal_photo_data:
            if meal_entry.get("image_url") and filename_to_match in meal_entry["image_url"]:
                matched_meal = meal_entry
                break
        
        if matched_meal:
            logged_meals_details.append(matched_meal)
            nutr = matched_meal.get("nutrition", {})
            total_consumed_today["kilojoules"] += nutr.get("kilojoules", 0)
            total_consumed_today["protein_grams"] += nutr.get("protein_grams", 0)
            total_consumed_today["fat_grams"] += nutr.get("fat_grams", 0)
            total_consumed_today["carbohydrate_grams"] += nutr.get("carbohydrate_grams", 0)
            total_consumed_today["fiber_grams"] += nutr.get("fiber_grams", 0)

    # Initialize/Update daily_nutrition_log
    if "daily_nutrition_log" not in profile_data or not isinstance(profile_data["daily_nutrition_log"], list):
        profile_data["daily_nutrition_log"] = []
    
    current_datetime_iso = datetime.now().isoformat()
    for meal_detail in logged_meals_details:
        profile_data["daily_nutrition_log"].append({
            "timestamp": current_datetime_iso,
            "source": "photo_log",
            "description": meal_detail.get("description"),
            "image_url": meal_detail.get("image_url"),
            "nutrition": meal_detail.get("nutrition"),
            "items": meal_detail.get("items")
        })

    # Initialize/Update daily_tracking_summary
    today_str = date.today().isoformat()
    nutritional_goals = profile_data.get("goals", {}).get("nutritional_goals", {})

    if "daily_tracking_summary" not in profile_data or \
        not isinstance(profile_data["daily_tracking_summary"], dict) or \
        profile_data["daily_tracking_summary"].get("date") != today_str:
        
        profile_data["daily_tracking_summary"] = {
            "date": today_str,
            "energy_quota": {
                "total_kj": nutritional_goals.get("daily_kilojoules"),
                "baseline_kj": nutritional_goals.get("daily_kilojoules"), # Assuming baseline is the total target for now
                "exercise_kj": 0 # Placeholder
            },
            "tracking_details": {
                "energy":    { "consumed_kj": 0, "target_kj": nutritional_goals.get("daily_kilojoules"), "unit": "kJ", "percentage": 0 },
                "protein":   { "consumed_g": 0, "target_g": nutritional_goals.get("protein_grams"), "unit": "g", "percentage": 0 },
                "fat":       { "consumed_g": 0, "target_g": nutritional_goals.get("fat_grams"), "unit": "g", "percentage": 0 },
                "carbs":     { "consumed_g": 0, "target_g": nutritional_goals.get("carbohydrate_grams"), "unit": "g", "percentage": 0 },
                "fiber":     { "consumed_g": 0, "target_g": nutritional_goals.get("fiber_grams"), "unit": "g", "percentage": 0 }
            }
        }
    
    # This is important if goals were recalculated but summary was for the same day
    summary_energy_quota = profile_data["daily_tracking_summary"]["energy_quota"]
    summary_tracking_details = profile_data["daily_tracking_summary"]["tracking_details"]

    summary_energy_quota["total_kj"] = nutritional_goals.get("daily_kilojoules")
    summary_energy_quota["baseline_kj"] = nutritional_goals.get("daily_kilojoules") # Re-affirm baseline assumption

    summary_tracking_details["energy"]["target_kj"] = nutritional_goals.get("daily_kilojoules")
    summary_tracking_details["protein"]["target_g"] = nutritional_goals.get("protein_grams")
    summary_tracking_details["fat"]["target_g"] = nutritional_goals.get("fat_grams")
    summary_tracking_details["carbs"]["target_g"] = nutritional_goals.get("carbohydrate_grams")
    summary_tracking_details["fiber"]["target_g"] = nutritional_goals.get("fiber_grams")

    # Add newly consumed amounts
    summary_tracking_details["energy"]["consumed_kj"] += total_consumed_today["kilojoules"]
    summary_tracking_details["protein"]["consumed_g"] += total_consumed_today["protein_grams"]
    summary_tracking_details["fat"]["consumed_g"] += total_consumed_today["fat_grams"]
    summary_tracking_details["carbs"]["consumed_g"] += total_consumed_today["carbohydrate_grams"]
    summary_tracking_details["fiber"]["consumed_g"] += total_consumed_today["fiber_grams"]

    # Recalculate percentages
    for nutrient_key, details_key, consumed_key, target_key in [
        ("energy", "energy", "consumed_kj", "target_kj"),
        ("protein", "protein", "consumed_g", "target_g"),
        ("fat", "fat", "consumed_g", "target_g"),
        ("carbs", "carbs", "consumed_g", "target_g"),
        ("fiber", "fiber", "consumed_g", "target_g")
    ]:
        consumed = summary_tracking_details[details_key][consumed_key]
        target = summary_tracking_details[details_key][target_key]
        summary_tracking_details[details_key]["percentage"] = round((consumed / (target or 1)) * 100) if target is not None else (100 if consumed > 0 else 0)


    await save_json_async(profile_path, profile_data)

    summary_for_ai = f"""
    Logged {len(logged_meals_details)} meal(s) from photos.
    The user's daily nutrition tracking summary has been updated and displayed to them.
    Key figures from today's summary:
    - Energy: {summary_tracking_details['energy']['consumed_kj']}/{summary_tracking_details['energy']['target_kj'] or 'N/A'} kJ
    - Protein: {summary_tracking_details['protein']['consumed_g']}/{summary_tracking_details['protein']['target_g'] or 'N/A'} g
    Please provide some very short, witty, and encouraging feedback to the user about their meal choices and today's summary so far.
    """
    if not logged_meals_details:
        summary_for_ai = "Meal nutrition estimation failed or no matching meals found for the provided photos."
        
    logger.info(f"Tool log_meal_photos_from_filenames summary for AI: {summary_for_ai}")
    return {
        "summary_for_ai": summary_for_ai,
        "updated_full_profile": copy.deepcopy(profile_data)
    }

################################################
###### Get Takeaway Recommendations Tool ######
################################################

RECOMMEND_HEALTHY_TAKEAWAY_TOOL_DEFINITION = {
    "type": "function",
    "name": "recommend_healthy_takeaway", # This name MUST match what's in config.py and app.py
    "description": (
        "Use this tool **whenever** the user asks for takeaway recommendations, help choosing takeaway, "
        "suggestions for what takeaway to get, mentions wanting to order food, or is looking for meal ideas for delivery. "
        "For example, if the user says: 'Any takeaway ideas?', 'What should I order tonight?', "
        "'Help me find a healthy takeaway.', 'I'm thinking of ordering in.', 'What are some good takeaway options?'. "
        "This tool provides data for 1-2 healthy takeaway meal suggestions which are then displayed in the user's UI. "
        "The tool's JSON output also includes a 'note_to_ai' field to guide your textual response to the user. "
        "**You MUST use this tool for such requests and DO NOT suggest takeaway dishes from your own knowledge.**"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "dietary_preferences": {
                "type": "string",
                "description": "Any specific dietary preferences or restrictions the user mentioned (e.g., 'vegetarian', 'low-carb'). (Currently ignored by the prototype version of the tool, but capture if provided)."
            },
            "number_of_options": {
                "type": "integer",
                "description": "Number of takeaway options to recommend. (Currently ignored by the prototype, which returns a fixed number)."
            }
        },
        "required": []
    }
}

async def get_takeaway_recommendations(user_data_dir: pathlib.Path, dietary_preferences: str = None, number_of_options: int = 2) -> str:
    """
    Tool implementation to fetch takeaway recommendations.
    Loads two fixed options from a JSON file.
    Returns a JSON string containing a note for the AI and the recommendation data.
    The recommendation data is intended for client display. The AI should use the note
    to formulate its textual response.
    
    Args:
        user_data_dir: Path to the user's data directory.
        dietary_preferences: (Ignored in this simplified version)
        number_of_options: (Ignored in this simplified version)
        
    Returns:
        JSON string of a payload containing 'note_to_ai' and 'recommendations'.
    """
    logger.info(f"Tool called: get_takeaway_recommendations (simplified version - always returns fixed options)")
    await asyncio.sleep(5) # Simulate processing delay
    
    base_data_dir = user_data_dir.parent 
    takeaway_json_path = base_data_dir / "nutrition" / TAKEAWAY_NUTRITION_FILENAME
    
    logger.info(f"Attempting to load takeaway data from: {takeaway_json_path}")

    all_options = await load_json_async(takeaway_json_path, default_return_type=list)

    if not all_options:
        logger.warning(f"No takeaway options loaded from {takeaway_json_path}.")
        # Prepare a note for the AI in case of no options
        note_to_ai_text = "I tried to find takeaway recommendations, but the data file seems to be empty or missing. Please inform the user that no options are available at the moment."
        return json.dumps({
            "note_to_ai": note_to_ai_text,
            "recommendations": []
        })

    selected_options = all_options[:2] 

    if not selected_options:
        note_to_ai_text = "I looked for takeaway options, but couldn't find any suitable ones from the available data. Please inform the user."
        return json.dumps({
            "note_to_ai": note_to_ai_text,
            "recommendations": []
        })

    # Craft the note for the AI
    note_to_ai_text = (
        f"The {len(selected_options)} takeaway recommendation(s) listed in the 'recommendations' key below have been prepared and already displayed to the user in their UI. "
        "Now, please provide a very short, witty, and encouraging comment about these choices. Do not read it out"
        "You MUST say something like: 'Based on the food you logged and exercises you have done today, "
        "I have worked out the energy and nutrition requirements for your dinner. "
        f"I have recommended two takeaway options for you. Both have a lot of fiber to meet today's target. Enjoy your meal!'"
    )

    payload = {
        "note_to_ai": note_to_ai_text,
        "recommendations": selected_options # This is what the client UI will use
    }
    
    logger.info(f"Returning fixed takeaway recommendations payload for LLM: {json.dumps(payload, indent=2)}")
    return json.dumps(payload)


################################################
###### Send Plain Email Tool ######
################################################

SEND_PLAIN_EMAIL_TOOL_DEFINITION = {
    "type": "function",
    "name": "send_plain_email",
    "description": (
        "Sends a plain text email to a specified recipient. "
        "Use this for sending simple messages, summaries, or follow-ups. "
        "Always confirm the recipient's email address and the main content of the email with the user before calling this tool."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "email_address": {
                "type": "string",
                "description": "The email address of the person to send the email to."
            },
            "subject": {
                "type": "string",
                "description": "The subject of the email."
            },
            "body": {
                "type": "string",
                "description": "The main text content of the email."
            }
        },
        "required": ["email_address", "subject", "body"]
    }
}

async def send_plain_email(email_address: str, subject: str, body: str):
    logger.info(f"Tool 'send_plain_email' called for {email_address} with subject '{subject}'")

    if not all([SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, DEFAULT_ORGANIZER_EMAIL]):
        logger.error("SMTP configuration is missing. Cannot send email.")
        return json.dumps({"status": "error", "message": "Server configuration error: SMTP settings not found."})

    sender_email = DEFAULT_ORGANIZER_EMAIL # Or SMTP_USERNAME, typically the same for this setup
    
    msg = MIMEMultipart() # Using MIMEMultipart allows for future expansion (e.g. HTML email)
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = email_address
    
    # Attach plain text body
    msg.attach(MIMEText(body, "plain"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(sender_email, email_address, msg.as_string())
        logger.info(f"Email sent to {email_address} with subject '{subject}'")
        return json.dumps({"status": "success", "message": f"Email with subject '{subject}' sent to {email_address}."})
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return json.dumps({"status": "error", "message": f"Failed to send email. Error: {e}"})