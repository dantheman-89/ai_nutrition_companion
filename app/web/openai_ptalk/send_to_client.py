import json
import pathlib
import asyncio

USER_PROFILE_FILENAME = "user_profile.json" # Consider moving to a shared constants file if used elsewhere

def _get_nested_value(data_dict, path, default=None):
    """Helper to safely get a value from a nested dictionary."""
    keys = path.split('.')
    val = data_dict
    for key in keys:
        if isinstance(val, dict) and key in val:
            val = val[key]
        else:
            return default
    return val

async def _read_user_profile(profile_path: pathlib.Path) -> dict:
    """Reads the user profile JSON file asynchronously."""
    try:
        if not await asyncio.to_thread(profile_path.exists):
            print(f"Profile file not found: {profile_path}")
            return {}
        
        content = await asyncio.to_thread(profile_path.read_text)
        return json.loads(content)
    except Exception as e:
        print(f"Error reading or parsing profile file {profile_path}: {e}")
        return {}


async def prepare_profile_for_display(user_data_dir: pathlib.Path) -> dict:
    """
    Reads, filters, renames, and restructures user profile data for frontend display.
    Outputs a dictionary ready to be sent as JSON.
    """
    profile_path = user_data_dir / USER_PROFILE_FILENAME
    profile_data = await _read_user_profile(profile_path)

    if not profile_data:
        return {} # Return empty if profile couldn't be loaded or is empty

    # Helper to process and add a section if it has content
    def process_section(source_data, renames_map, is_list_join_fields=None):
        section_dict = {}
        if is_list_join_fields is None:
            is_list_join_fields = []
        for old_key, new_key in renames_map.items():
            value = _get_nested_value(source_data, old_key)
            if value is not None:
                if old_key in is_list_join_fields and isinstance(value, list):
                    section_dict[new_key] = ", ".join(map(str, value)) if value else "N/A"
                elif isinstance(value, bool): # Convert booleans to Yes/No
                    section_dict[new_key] = "Yes" if value else "No"
                else:
                    section_dict[new_key] = value
        return section_dict

    ui_profile = {}

    # 1. Basic Information
    basic_info_renames = {
        "preferred_name": "Name", "age_years": "Age", "sex": "Sex",
        "height_cm": "Height (cm)", "weight_kg": "Weight (kg)", "bmi_kg_m2": "BMI"
    }
    basic_info_data = process_section(_get_nested_value(profile_data, "basic_info", {}), basic_info_renames)
    if basic_info_data:
        ui_profile["Basic Information"] = basic_info_data

    # 2. Dietary Preferences & Eating Habits (combined)
    diet_habits_data = {}
    diet_pref = _get_nested_value(profile_data, "dietary_preferences", {})
    eating_habits_val = _get_nested_value(profile_data, "eating_habits.eating_habits")

    if diet_pref.get("culture") is not None:
        diet_habits_data["Cultural Background"] = diet_pref["culture"]
    if diet_pref.get("food_preferences") is not None:
        fp_list = diet_pref["food_preferences"]
        diet_habits_data["Food Preferences"] = ", ".join(fp_list) if fp_list else "N/A"
    if diet_pref.get("allergies") is not None:
        al_list = diet_pref["allergies"]
        diet_habits_data["Allergies"] = ", ".join(al_list) if al_list else "N/A"
    if eating_habits_val is not None:
        diet_habits_data["General Eating Habits"] = eating_habits_val
    
    if diet_habits_data:
        ui_profile["Diet & Habits"] = diet_habits_data

    # 3. Goals (Weight Goals & general goal status)
    goals_section_data = {}
    weight_goals_data = process_section(
        _get_nested_value(profile_data, "goals.weight_goals", {}),
        {"target_weight_kg": "Target Weight (kg)", "goal_timeframe_weeks": "Goal Timeframe (weeks)"}
    )
    goals_section_data.update(weight_goals_data)

    if goals_section_data:
        ui_profile["Weight Goals"] = goals_section_data
        
    # 4. Nutritional Targets (from goals.nutritional_goals)
    nutritional_targets_renames = {
        "daily_kilojoules": "Daily Kilojoules", "protein_grams": "Protein (g)",
        "fat_grams": "Fat (g)", "carbohydrate_grams": "Carbohydrate (g)", "fiber_grams": "Fiber (g)"
    }
    nutritional_targets_data = process_section(
        _get_nested_value(profile_data, "goals.nutritional_goals", {}),
        nutritional_targets_renames
    )
    if nutritional_targets_data:
        ui_profile["Nutritional Targets (Baseline)"] = nutritional_targets_data

    # 5. Vitality Information
    vitality_ui_data = {}
    vitality_source = _get_nested_value(profile_data, "vitality_information", {})
    
    if vitality_source.get("status") is not None:
        vitality_ui_data["Vitality Status"] = vitality_source["status"]

    points_renames = {
        "current_year": "Current Year Points",
        "goal_for_diamond": "Points for Diamond",
        "weekly_active_rewards_streak": "Weekly Active Rewards Streak"
    }
    points_data = process_section(_get_nested_value(vitality_source, "points", {}), points_renames)
    vitality_ui_data.update(points_data)

    health_checks_renames = {
        "last_vitality_health_check": "Last Vitality Health Check",
        "weight": "Weight (kg)", "height": "Height (cm)", "bmi": "BMI",
        "blood_pressure": "Blood Pressure", "glucose": "Glucose", "LDL_cholesterol": "LDL Cholesterol"
    }
    health_checks_data = process_section(_get_nested_value(vitality_source, "health_checks", {}), health_checks_renames)
    vitality_ui_data.update(health_checks_data)

    if vitality_ui_data:
        ui_profile["Vitality Health Summary"] = vitality_ui_data
        
    return ui_profile
