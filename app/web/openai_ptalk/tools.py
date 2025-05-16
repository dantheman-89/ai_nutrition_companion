import json
import pathlib
from typing import Dict, Any

# File paths
USER_PROFILE_FILENAME = "user_profile.json"
VITALITY_DATA_FILENAME = "vitality_data.json"
HEALTHY_SWAP_FILENAME = "healthy_swap.json"

# ─────────────────────────────────────────────────────────────────────────────
# Tool Functions - LLM definition + function implementation
# ─────────────────────────────────────────────────────────────────────────────

###### Helper function ######
def calculate_bmi(height_cm: float, weight_kg: float) -> float:
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

###### Profile update tool ######
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
        if user_profile_path.exists():
            with open(user_profile_path, 'r') as f:
                profile_data = json.load(f)
        
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
        if "height" in fields_to_update and "weight" in fields_to_update:
            if "basic_info" not in profile_data:
                profile_data["basic_info"] = {}
            profile_data["basic_info"]["bmi_kg_m2"] = calculate_bmi(fields_to_update["height"], fields_to_update["weight"])

        # Check if we have all required fields to calculate nutrition targets
        profile_data = check_goal_calculation_readiness(profile_data)

        # Write back to the file
        with open(user_profile_path, 'w') as f:
            json.dump(profile_data, f, indent=2)
        print(f"Updated profile with fields: {', '.join(fields_to_update.keys())}")
        
    except Exception as e:
        print(f"Error updating profile JSON: {e}")
    
    # Return the updated profile as a JSON string
    return json.dumps(profile_data)
        
        
###### Load External Health Data ######
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
    
    print(f"Executing load_vitality_data tool. Attempting to read: {vitality_data_path}")
    
    try:
        # 1. Read Vitality data
        with open(vitality_data_path, 'r') as f:
            vitality_data = json.load(f)
            print(f"Successfully loaded data from {vitality_data_path}")
        
        # 2. Load existing user profile
        profile_data = {}
        if user_profile_path.exists():
            try:
                with open(user_profile_path, 'r') as f:
                    profile_data = json.load(f)
            except Exception as e:
                print(f"Error reading existing profile {user_profile_path}: {e}. Starting fresh.")
        
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
        
        # 6. Check if we have all required fields to calculate nutrition targets
        profile_data = check_goal_calculation_readiness(profile_data)
        
        # 7. Write updated profile back
        with open(user_profile_path, 'w') as f:
            json.dump(profile_data, f, indent=2)
        print(f"Successfully updated {user_profile_path} with data from {vitality_data_path}")
        
        # 8. Return the full profile data as a JSON string for LLM use
        return json.dumps(profile_data, indent=2)
        
    except Exception as e:
        error_msg = f"Error processing file {vitality_data_path} or updating profile {user_profile_path}: {e}"
        print(error_msg)

    
###### Load Healthy Swap Data ######
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
            with open(healthy_swap_path, 'r') as f:
                healthy_swaps_data = json.load(f)
                print(f"Successfully loaded healthy swaps data from {healthy_swap_path}")
                
            # Update user profile with this data
            if user_profile_path.exists():
                try:
                    with open(user_profile_path, 'r') as f:
                        profile_data = json.load(f)
                    
                    # Update the healthy_swaps section
                    profile_data["healthy_swaps"] = healthy_swaps_data
                    
                    # Write updated profile back
                    with open(user_profile_path, 'w') as f:
                        json.dump(profile_data, f, indent=2)
                    print(f"Updated user profile with healthy swaps data")
                except Exception as e:
                    print(f"Error updating user profile: {e}")
        else:
            print(f"Dedicated healthy_swap.json not found")
            healthy_swaps_data = {
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



###### Calculate Nutrition Targets ######
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
        if not user_profile_path.exists():
            return json.dumps({"error": "User profile not found"})
            
        with open(user_profile_path, 'r') as f:
            profile_data = json.load(f)
        
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
        with open(user_profile_path, 'w') as f:
            json.dump(profile_data, f, indent=2)
        
        # 13. Return the nutrition targets as a JSON string
        return json.dumps(nutrition_targets, indent=2)
        
    except Exception as e:
        error_msg = f"Error calculating nutrition targets: {str(e)}"
        print(error_msg)