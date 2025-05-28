import json
import pathlib
from datetime import datetime, timedelta, date
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
WEEKLY_SUMMARY_FILENAME = "weekly_summary.json"

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

def check_goal_calculation_readiness(profile_data: dict) -> tuple[dict, str | None]:
    """
    Checks if the profile contains all information required to calculate nutrition targets,
    updates the ready_to_calculate_goal flag, and generates a 'note_to_ai' for guidance.
    
    Required fields for goal calculation:
    - weight_kg, target_weight_kg, goal_timeframe_weeks, height_cm, age_years, sex
    
    Also checks for dietary preferences, allergies, and eating habits for conversational flow.
    
    Args:
        profile_data: The user profile data dictionary
        
    Returns:
        A tuple containing:
            - Updated profile data with ready_to_calculate_goal set appropriately.
            - A 'note_to_ai' string for LLM guidance, or None if no specific note is needed.
    """
    if "goals" not in profile_data:
        profile_data["goals"] = {}
    
    # Check for all required fields for goal calculation
    has_weight = get_nested_value(profile_data, "basic_info.weight_kg") is not None
    has_target_weight = get_nested_value(profile_data, "goals.weight_goals.target_weight_kg") is not None
    has_timeframe = get_nested_value(profile_data, "goals.weight_goals.goal_timeframe_weeks") is not None
    has_height = get_nested_value(profile_data, "basic_info.height_cm") is not None
    has_age = get_nested_value(profile_data, "basic_info.age_years") is not None
    has_sex = get_nested_value(profile_data, "basic_info.sex") is not None
    
    ready_to_calculate = all([
        has_weight, has_target_weight, has_timeframe,
        has_height, has_age, has_sex
    ])
    
    profile_data["goals"]["ready_to_calculate_goal"] = ready_to_calculate
    # print(f"Profile readiness for goal calculation: {ready_to_calculate}") # Optional: keep for debugging

    # --- Start of note_to_ai logic ---
    note_to_ai = None
    goal_set = get_nested_value(profile_data, "goals.goal_set", False)

    missing_basic_info_for_goals = []
    if not has_weight: missing_basic_info_for_goals.append("current weight")
    if not has_target_weight: missing_basic_info_for_goals.append("target weight")
    if not has_timeframe: missing_basic_info_for_goals.append("goal timeframe")
    if not has_height: missing_basic_info_for_goals.append("height")
    if not has_age: missing_basic_info_for_goals.append("age")
    if not has_sex: missing_basic_info_for_goals.append("sex")

    missing_dietary_prefs = not get_nested_value(profile_data, "dietary_preferences.food_preferences")
    missing_allergies = not get_nested_value(profile_data, "dietary_preferences.allergies")
    eating_habits_data = get_nested_value(profile_data, "eating_habits.eating_habits")
    missing_eating_habits = not eating_habits_data 

    needs_dietary_info = missing_dietary_prefs or missing_allergies or missing_eating_habits
    missing_dietary_details = []
    if missing_dietary_prefs: missing_dietary_details.append("food preferences")
    if missing_allergies: missing_dietary_details.append("allergies")
    if missing_eating_habits: missing_dietary_details.append("eating habits")

    if not goal_set:
        # Priority 1: Missing basic information for goal calculation
        if missing_basic_info_for_goals:
            first_missing_basic = missing_basic_info_for_goals[0]
            note_to_ai = f"To proceed with goal setting, I need a bit more information. Please ask the user for their {first_missing_basic}."
        
        # Priority 2: Basic info is complete, but missing dietary details
        elif needs_dietary_info: # This implies ready_to_calculate is True (or would be if not for dietary)
            # Determine the first missing dietary detail to ask for
            first_missing_dietary = ""
            if missing_dietary_prefs: first_missing_dietary = "food preferences"
            elif missing_allergies: first_missing_dietary = "allergies"
            elif missing_eating_habits: first_missing_dietary = "eating habits"
            
            if first_missing_dietary:
                note_to_ai = f"Thanks! We have the basics. To better tailor the nutrition plan, please ask the user about their {first_missing_dietary} next."

        # Priority 3: All information is present
        elif ready_to_calculate and not needs_dietary_info: 
            note_to_ai = "Excellent, I have all the information needed to calculate baseline nutrition targets. Please ask the user if they would like to do that now."
        
        elif not note_to_ai: # Fallback
             note_to_ai = "It looks like we still need some information before we can set nutrition goals. Please continue gathering profile details."

    else: # Goal is already set
        note_to_ai = "Nutrition goals are already set."
        if needs_dietary_info: 
            first_missing_dietary_fallback = missing_dietary_details[0] if missing_dietary_details else "further dietary details"
            note_to_ai += f" However, I don't seem to have the user's {first_missing_dietary_fallback} on file. If the conversation allows, you could ask for this to refine future recommendations."
    
    return profile_data, note_to_ai

################################################
###### Profile update tool ######
################################################

PROFILE_TOOL_DEFINITION = {
    "type": "function",
    "name": "update_user_profile",
    "description": "Updates or records user's health and preference information such as height, weight, target weight, goal timeframe, age, sex, culture, food preferences, allergies, or eating habits. Use this to gather information needed for profile completion and goal setting. The tool will return a 'note_to_ai' guiding your next actions.",
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
    Returns a JSON string with 'profile_data' and a 'note_to_ai' for LLM guidance.
    
    Args:
        user_data_dir: Path to the user profile JSON file
        fields_to_update: Dictionary of fields to update from LLM
    
    Returns:
        JSON string containing the updated user profile under 'profile_data' and a 'note_to_ai'.
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
    generated_note_to_ai = "Profile update processed." # Default note

    try:
        # Load existing profile if it exists
        profile_data = await load_json_async(user_profile_path, default_return_type=dict)
        
        # Process each field using the mapping
        for field, value in fields_to_update.items():
            if field in field_mapping:
                path = field_mapping[field].split('.')
                current = profile_data
                for i, key in enumerate(path[:-1]):
                    if key not in current:
                        current[key] = {}
                    current = current[key]
                current[path[-1]] = value
            else:
                profile_data[field] = value

        # Calculate BMI if both height and weight are available
        if "height" in fields_to_update or "weight" in fields_to_update:
            if "basic_info" not in profile_data:
                profile_data["basic_info"] = {}
            basic_info_data = profile_data.get("basic_info", {})
            current_height_cm = basic_info_data.get("height_cm")
            current_weight_kg = basic_info_data.get("weight_kg")
            if current_height_cm is not None and current_weight_kg is not None:
                profile_data["basic_info"]["bmi_kg_m2"] = calculate_bmi(current_height_cm, current_weight_kg)

        # Call check_goal_calculation_readiness. It updates profile_data internally with the readiness flag
        # and returns the (now updated) profile_data and the separate note.
        profile_data_with_readiness, generated_note_to_ai = check_goal_calculation_readiness(profile_data)

        # Save the profile_data that includes the readiness flag (but NOT the transient note itself)
        await save_json_async(user_profile_path, profile_data_with_readiness)
        print(f"Updated profile with fields: {', '.join(fields_to_update.keys())}")
        
        # Construct the payload for the LLM
        llm_payload = {
            "profile_data": profile_data_with_readiness,
            "note_to_ai": generated_note_to_ai
        }
        return json.dumps(llm_payload)
        
    except Exception as e:
        print(f"Error updating profile JSON: {e}")
        error_payload = {
            "profile_data": profile_data, # Return potentially partially updated data or last known good
            "note_to_ai": f"An error occurred updating the profile: {str(e)}. Please check logs and inform the user if necessary.",
            "error": str(e) 
        }
        return json.dumps(error_payload)
        
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
    Loads external health data, updates the user profile, and returns a JSON string
    containing 'profile_data' and a consolidated 'note_to_ai'.
    
    Args:
        user_data_dir: Path to the user data directory.
        
    Returns:
        JSON string for LLM use.
    """
    vitality_data_path = user_data_dir / VITALITY_DATA_FILENAME
    user_profile_path = user_data_dir / USER_PROFILE_FILENAME
    stale_data_message = None # To store the message about stale data
    profile_data = {} # Initialize to ensure it's defined in error cases too
    
    print(f"Executing load_vitality_data tool. Attempting to read: {vitality_data_path}")
    
    try:
        # 1. Read Vitality data
        vitality_data = await load_json_async(vitality_data_path, default_return_type=dict)
        
        # 2. Load existing user profile
        profile_data = await load_json_async(user_profile_path, default_return_type=dict)
        if not profile_data:
            logger.warning(f"User profile {user_profile_path} not found or empty. Starting fresh.")
            profile_data = {}
        
        # 3. Extract and map basic information (omitted for brevity, same as your existing code)
        # ... your existing logic to merge vitality_data into profile_data ...
        basic_info = vitality_data.get("basic", {})
        if isinstance(basic_info, dict):
            if "basic_info" not in profile_data: profile_data["basic_info"] = {}
            if "preferred_name" in basic_info: profile_data["basic_info"]["preferred_name"] = basic_info["preferred_name"]
            if "age_years" in basic_info: profile_data["basic_info"]["age_years"] = basic_info["age_years"]
            if "sex" in basic_info: profile_data["basic_info"]["sex"] = basic_info["sex"]
        
        if "status" in vitality_data:
            if "vitality_information" not in profile_data: profile_data["vitality_information"] = {}
            profile_data["vitality_information"]["status"] = vitality_data["status"]
        if "points" in vitality_data:
            if "vitality_information" not in profile_data: profile_data["vitality_information"] = {}
            profile_data["vitality_information"]["points"] = vitality_data["points"]
        if "recent_activities" in vitality_data:
            if "vitality_information" not in profile_data: profile_data["vitality_information"] = {}
            profile_data["vitality_information"]["recent_activities"] = vitality_data["recent_activities"]
        if "exercise_energy" in vitality_data:
            if "vitality_information" not in profile_data: profile_data["vitality_information"] = {}
            profile_data["vitality_information"]["exercise_energy"] = vitality_data["exercise_energy"]
        
        health_checks = vitality_data.get("health_checks", {})
        if isinstance(health_checks, dict):
            if "vitality_information" not in profile_data: profile_data["vitality_information"] = {}
            if "health_checks" not in profile_data["vitality_information"]: profile_data["vitality_information"]["health_checks"] = {}
            for key, value in health_checks.items():
                profile_data["vitality_information"]["health_checks"][key] = value
            
            # Update basic_info with height and weight from health_checks if available
            vitality_height_cm = health_checks.get("height")
            vitality_weight_kg = health_checks.get("weight")

            if vitality_height_cm is not None:
                profile_data["basic_info"]["height_cm"] = float(vitality_height_cm)
                logger.info(f"Updated profile height from Vitality: {vitality_height_cm} cm")
            if vitality_weight_kg is not None:
                profile_data["basic_info"]["weight_kg"] = float(vitality_weight_kg)
                logger.info(f"Updated profile weight from Vitality: {vitality_weight_kg} kg")

            # Recalculate BMI if both height and weight are now in basic_info
            current_height_cm = profile_data["basic_info"].get("height_cm")
            current_weight_kg = profile_data["basic_info"].get("weight_kg")
            if current_height_cm is not None and current_weight_kg is not None:
                bmi = calculate_bmi(current_height_cm, current_weight_kg)
                if bmi is not None:
                    profile_data["basic_info"]["bmi_kg_m2"] = bmi
                    logger.info(f"Recalculated BMI: {bmi}")

            # Stale data check (based on weight from Vitality health_checks)
            last_check_date_str = health_checks.get("last_vitality_health_check")

            if last_check_date_str and current_weight_kg is not None: # Only consider stale if weight was present
                try:
                    last_check_date = datetime.strptime(last_check_date_str, "%Y-%m-%d")
                    six_months_ago = datetime.now() - timedelta(days=6*30) 
                    if last_check_date < six_months_ago:
                        stale_data_message = "Your weight data from Vitality is more than 6 months out of date. Please tell the user about this and ask for their latest weight."
                        logger.info("Vitality weight/height data is more than 6 months old.")
                except ValueError:
                    logger.info(f"Could not parse last_vitality_health_check date: {last_check_date_str}")


        profile_data_with_readiness, note_from_readiness_check = check_goal_calculation_readiness(profile_data)
        
        await save_json_async(user_profile_path, profile_data_with_readiness)
        logger.info(f"Successfully updated {user_profile_path} with data from {vitality_data_path}")
        
        # Construct the final note_to_ai for the LLM
        final_note_to_ai = "Vitality data loaded." # Base message

        if stale_data_message:
            # If data is stale, this is the primary instruction.
            # The next user interaction (providing weight) will trigger update_profile,
            # which will then run check_goal_calculation_readiness for the next step.
            final_note_to_ai = stale_data_message # Overwrite base, make this the sole focus
        elif note_from_readiness_check:
            # If no stale data message, then the readiness check note is the main guidance.
            final_note_to_ai += f" {note_from_readiness_check}" # Append to "Vitality data loaded."
        else:
            # If no stale message and no specific readiness note (e.g., goals already set and all info present)
            final_note_to_ai += " Profile status checked."

        llm_payload = {
            "profile_data": profile_data_with_readiness,
            "note_to_ai": final_note_to_ai
        }
        return json.dumps(llm_payload, indent=2)
        
    except Exception as e:
        error_msg = f"Error processing file {vitality_data_path} or updating profile {user_profile_path}: {e}"
        print(error_msg)
        error_payload = {
            "profile_data": profile_data, # Return profile_data as it was before error, or empty
            "note_to_ai": f"An error occurred while loading Vitality data: {error_msg}. Please inform the user and check logs.",
            "error": error_msg # Keep error field for debugging if needed, but LLM focuses on note_to_ai
        }
        return json.dumps(error_payload)


################################################    
###### Load Healthy Swap Data ######
################################################

LOAD_HEALTHY_SWAP_TOOL_DEFINITION = {
    "type": "function",
    "name": "load_healthy_swap",
    "description": (
        "Loads personalized healthy food swap recommendations for the user. "
        "These recommendations are based on their recent grocery shopping data "
        "and aim to improve dietary choices by suggesting swaps towards healthier food items. "
        "Use this when the user asks for healthy swaps, ways to improve their shopping, or as a next step after setting nutrition goals. "
        "The tool output includes a 'note_to_ai' to guide your response and 'recommendations' for the user."
    ),
    "parameters": {
        "type": "object",
        "properties": {}, # No parameters needed
        "required": []
    }
}

async def load_healthy_swap(user_data_dir: pathlib.Path) -> str:
    """
    Loads healthy food swap data for the user from the dedicated healthy_swap.json file,
    updates the user_profile.json with this data, and returns a structured JSON payload
    for the LLM, including a 'note_to_ai' and the swap recommendations.
    
    Args:
        user_data_dir: Path to the user data directory.
        
    Returns:
        JSON string containing a note for the AI and the healthy swaps data.
    """
    healthy_swap_path = user_data_dir / HEALTHY_SWAP_FILENAME
    user_profile_path = user_data_dir / USER_PROFILE_FILENAME
    
    logger.info(f"Executing load_healthy_swap tool. Attempting to read: {healthy_swap_path}")
    
    try:
        healthy_swaps_data = await load_json_async(healthy_swap_path, default_return_type=dict)
        
        if not healthy_swaps_data or not healthy_swaps_data.get("recommended_swaps"):
            logger.info(f"Healthy_swap.json not found, empty, or has no recommendations at {healthy_swap_path}")
            note_to_ai = "I checked for healthy food swap recommendations, but none are currently available for the user. You can inform them of this."
            payload = {
                "note_to_ai": note_to_ai,
                "recommendations": []
            }
        else:
            # Update user profile with this data
            profile_data = await load_json_async(user_profile_path, default_return_type=dict)
            if not isinstance(profile_data, dict): # Ensure profile_data is a dict
                profile_data = {}
            profile_data["healthy_swaps"] = copy.deepcopy(healthy_swaps_data) # Store a copy
            await save_json_async(user_profile_path, profile_data)
            logger.info(f"Updated user profile with healthy swaps data from {healthy_swap_path}")

            recommendations = healthy_swaps_data.get("recommended_swaps", [])
            notes_from_data = healthy_swaps_data.get("notes", "General recommendations to improve diet.") # This was overall_notes
            num_recommendations = len(recommendations)

            ai_summary_parts = [
                f"The user has {num_recommendations} personalized healthy food swap recommendation(s) available."
            ]
            rec_titles = [rec.get('title', 'a recommendation') for rec in recommendations if isinstance(rec, dict)]
            if rec_titles:
                ai_summary_parts.append(f"Key recommendations include: {'; '.join(rec_titles)}.")

            # Incorporate notes_from_data (previously overall_notes) into the AI summary
            if notes_from_data:
                 ai_summary_parts.append(f"The general guidance for these swaps is: '{notes_from_data}'.")

            ai_summary_parts.append(
                "Full details are provided in the 'recommendations' list below. "
                "When presenting to the user, please clearly explain the 'observation' (why the swap is suggested), "
                "the 'action' (what to swap), and the 'rationale' (the benefit) for each swap. "
                "Keep it very succient and under 45 seconds."
            )
            note_to_ai = " ".join(ai_summary_parts)
            
            payload = {
                "note_to_ai": note_to_ai,
                "recommendations": recommendations
            }

        return json.dumps(payload, indent=2)

    except Exception as e:
        error_msg = f"Error in load_healthy_swap: {e}"
        logger.error(error_msg, exc_info=True)
        return json.dumps({
            "note_to_ai": f"I encountered an error while trying to fetch healthy swap recommendations: {str(e)}. Please inform the user and suggest trying again later.",
            "recommendations": [],
            # "error": error_msg # Removed error from payload to match the two-item requirement, error is in note_to_ai
        })
       
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
    profile_data = {}

    try:
        # 1. Load user profile
        profile_data = await load_json_async(user_profile_path, default_return_type=dict)
        if not profile_data:
            return json.dumps({
                "error": "User profile not found or empty",
                "note_to_ai": "I couldn't calculate nutrition targets because the user profile is missing or empty. Please try gathering some basic information first."
            })
        
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
            missing_fields_str = ', '.join(missing_fields)
            return json.dumps({
                "error": f"Missing required profile fields: {missing_fields_str}",
                "note_to_ai": f"I couldn't calculate nutrition targets because some information is missing: {missing_fields_str}. Please ask the user for this information."
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
        profile_data["goals"]["nutritional_goals"] = nutrition_targets
        profile_data["goals"]["goal_set"] = True
        
        # 12. Initialize/Reset daily_tracking_summary for today with new targets
        today_str = datetime.now().date().isoformat() # Use date part of datetime
        
        # Always reset the summary for today if targets are (re)calculated
        exercise_energy = (profile_data.get("vitality_information", {}).get("exercise_energy", [{}])[0].get("kilojoules", 0) if profile_data.get("vitality_information", {}).get("exercise_energy") else 0)
        profile_data["daily_tracking_summary"] = {
            "date": today_str,
            "energy_quota": {
                "total_kj": nutrition_targets.get("daily_kilojoules") + exercise_energy,
                "baseline_kj": nutrition_targets.get("daily_kilojoules"),
                "exercise_kj": exercise_energy
            },
            "tracking_details": {
                "energy":    { "consumed_kj": 0, "target_kj": nutrition_targets.get("daily_kilojoules"), "unit": "kJ", "percentage": 0 },
                "protein":   { "consumed_g": 0, "target_g": nutrition_targets.get("protein_grams"), "unit": "g", "percentage": 0 },
                "fat":       { "consumed_g": 0, "target_g": nutrition_targets.get("fat_grams"), "unit": "g", "percentage": 0 },
                "carbs":     { "consumed_g": 0, "target_g": nutrition_targets.get("carbohydrate_grams"), "unit": "g", "percentage": 0 },
                "fiber":     { "consumed_g": 0, "target_g": nutrition_targets.get("fiber_grams"), "unit": "g", "percentage": 0 }
            }
        }
        # If daily_nutrition_log for today exists, it should be preserved, but this function focuses on targets.
        # If there was already a log for today, its consumed values would be re-summed by the logging function if it runs again.
        # For simplicity here, we reset consumed to 0, assuming this is a fresh start for the day's tracking against new targets.

        # 13. Write updated profile back to file
        await save_json_async(user_profile_path, profile_data)
        
        # 14. Return the nutrition targets and a note_to_ai as a JSON string
        note_to_ai = (
            "Baseline daily nutrition targets have been calculated and saved. "
            "The user's tracking for today has been updated with these new targets. "
            "You can now discuss these targets with the user and explain them."
        )
        return json.dumps({
            "nutrition_targets": nutrition_targets,
            "note_to_ai": note_to_ai
        }, indent=2)
        
    except Exception as e:
        error_msg = f"Error calculating nutrition targets: {str(e)}"
        logger.error(error_msg, exc_info=True) # Use logger
        return json.dumps({
            "error": error_msg,
            "note_to_ai": "An unexpected error occurred while trying to calculate nutrition targets. Please inform the user and check the logs."
        })


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
        
        exercise_energy = (profile_data.get("vitality_information", {}).get("exercise_energy", [{}])[0].get("kilojoules", 0) if profile_data.get("vitality_information", {}).get("exercise_energy") else 0)
        profile_data["daily_tracking_summary"] = {
            "date": today_str,
            "energy_quota": {
                "total_kj": nutritional_goals.get("daily_kilojoules") + exercise_energy,
                "baseline_kj": nutritional_goals.get("daily_kilojoules"),
                "exercise_kj": exercise_energy
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
    await asyncio.sleep(3) # Simulate processing delay
    
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
        "We also saw the user did a 1 hour workout today with gave them 1500 kj extra energy budget. "
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
###### Get Weekly Review Data Tool ######
################################################

GET_WEEKLY_REVIEW_TOOL_DEFINITION = {
    "type": "function",
    "name": "get_weekly_review_data",
    "description": "An internal tool that loads the user's weekly nutrition summary. This tool is triggered by the system when the user requests their weekly review. Do not call this tool directly.",
    "parameters": {
        "type": "object",
        "properties": {}, # No parameters needed as it reads a fixed file for the user
        "required": []
    }
}

async def get_weekly_review_data_for_llm(user_data_dir: pathlib.Path) -> dict:
    """
    Loads the weekly summary data for the user.
    Returns a dictionary containing a summary for the AI and the raw data for the client.
    """
    weekly_summary_path = user_data_dir / WEEKLY_SUMMARY_FILENAME
    logger.info(f"Tool: get_weekly_review_data_for_llm attempting to load {weekly_summary_path}")
    await asyncio.sleep(0.5) # Simulate short processing delay

    weekly_data = await load_json_async(weekly_summary_path, default_return_type=dict)

    if not weekly_data:
        logger.warning(f"Weekly summary data not found or empty at {weekly_summary_path}")
        return {
            "summary_for_ai": "I tried to load the weekly review, but the data seems to be missing. Please inform the user.",
            "raw_data_for_client": {}
        }

    # Basic summarization for the AI
    total_energy_actual = get_nested_value(weekly_data, "weekly_review_summary.total_energy.actual_kj", 0)
    total_energy_target = get_nested_value(weekly_data, "weekly_review_summary.total_energy.target_kj", 0)
    period_label = get_nested_value(weekly_data, 'weekly_review_summary.period_label', 'the period')

    daily_breakdown_summary_parts = []
    daily_energy_data = weekly_data.get("daily_energy_breakdown", [])
    if daily_energy_data:
        for day_data in daily_energy_data:
            day_label = day_data.get("day_label", "A day")
            actual_kj = day_data.get("actual_kj", 0)
            target_kj = day_data.get("target_kj", 0)
            if target_kj > 0:
                percentage_diff = ((actual_kj - target_kj) / target_kj) * 100
                if percentage_diff > 0:
                    daily_breakdown_summary_parts.append(f"{day_label}: {percentage_diff:.0f}% over target")
                elif percentage_diff < 0:
                    daily_breakdown_summary_parts.append(f"{day_label}: {abs(percentage_diff):.0f}% under target")
                else:
                    daily_breakdown_summary_parts.append(f"{day_label}: on target")
            else:
                daily_breakdown_summary_parts.append(f"{day_label}: {actual_kj} kJ (no target)")
    
    daily_summary_str = "; ".join(daily_breakdown_summary_parts)

    overall_weekly_percentage_diff = 0
    if total_energy_target > 0:
        overall_weekly_percentage_diff = ((total_energy_actual - total_energy_target) / total_energy_target) * 100
    
    overall_summary_str = ""
    if overall_weekly_percentage_diff > 0:
        overall_summary_str = f"Overall for {period_label}, total energy intake was {total_energy_actual} kJ against a target of {total_energy_target} kJ, which is {overall_weekly_percentage_diff:.0f}% over target."
    elif overall_weekly_percentage_diff < 0:
        overall_summary_str = f"Overall for {period_label}, total energy intake was {total_energy_actual} kJ against a target of {total_energy_target} kJ, which is {abs(overall_weekly_percentage_diff):.0f}% under target."
    else:
        overall_summary_str = f"Overall for {period_label}, total energy intake was {total_energy_actual} kJ, right on the target of {total_energy_target} kJ."


    summary_for_ai = (
        f"The user's weekly nutrition summary for {period_label} has been loaded and displayed in their UI. "
        f"{overall_summary_str} "
        f"Daily breakdown: {daily_summary_str}. "
        "Please provide a brief, encouraging comment. If you notice a pattern (e.g., consistently over/under on certain days like weekends), "
        "gently point it out and ask an open-ended question to understand why and if they'd like to discuss strategies. "
        "Avoid re-stating all the numbers as they can see the details."
    )
    
    logger.info(f"Tool get_weekly_review_data_for_llm summary for AI: {summary_for_ai}")
    return {
        "summary_for_ai": summary_for_ai,
        "raw_data_for_client": weekly_data 
    }



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

    # Start the email sending in background without waiting
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _send_email_sync, email_address, subject, body)
    
    # Return immediately with success message
    logger.info(f"Email queued for sending to {email_address} with subject '{subject}'")
    return json.dumps({"status": "success", "message": f"I have sent the email to {email_address}."})

def _send_email_sync(email_address: str, subject: str, body: str):
    """Synchronous email sending function to run in executor"""
    try:
        sender_email = DEFAULT_ORGANIZER_EMAIL
        
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = sender_email
        msg["To"] = email_address
        
        # Attach plain text body
        msg.attach(MIMEText(body, "plain"))

        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(sender_email, email_address, msg.as_string())
        
        logger.info(f"Email successfully sent to {email_address} with subject '{subject}'")
    except Exception as e:
        logger.error(f"Failed to send email to {email_address}: {e}")