import json
import pathlib
import asyncio
from datetime import datetime
import logging
from .util import load_json_async, get_nested_value # Changed from get_nested_value

logger = logging.getLogger(__name__)

USER_PROFILE_FILENAME = "user_profile.json" # Consider moving to a shared constants file if used elsewhere

# ------------------------------------#
# Prepare Profile for Display
# ------------------------------------#
async def prepare_profile_for_display(user_data_dir: pathlib.Path) -> dict:
    """
    Reads, filters, renames, and restructures user profile data for frontend display.
    Outputs a dictionary ready to be sent as JSON.
    """
    profile_path = user_data_dir / USER_PROFILE_FILENAME
    profile_data = await load_json_async(profile_path, default_return_type=dict)

    if not profile_data:
        return {} # Return empty if profile couldn't be loaded or is empty

    # Helper to process and add a section if it has content
    def process_section(source_data, renames_map, is_list_join_fields=None):
        section_dict = {}
        if is_list_join_fields is None:
            is_list_join_fields = []
        for old_key, new_key in renames_map.items():
            value = get_nested_value(source_data, old_key)
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
    basic_info_data = process_section(get_nested_value(profile_data, "basic_info", {}), basic_info_renames)
    if basic_info_data:
        ui_profile["Basic Information"] = basic_info_data

    # 2. Dietary Preferences & Eating Habits (combined)
    diet_habits_data = {}
    diet_pref = get_nested_value(profile_data, "dietary_preferences", {})
    eating_habits_val = get_nested_value(profile_data, "eating_habits.eating_habits")

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
        get_nested_value(profile_data, "goals.weight_goals", {}),
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
        get_nested_value(profile_data, "goals.nutritional_goals", {}),
        nutritional_targets_renames
    )
    if nutritional_targets_data:
        ui_profile["Nutritional Targets (Baseline)"] = nutritional_targets_data

    # 5. Vitality Information
    vitality_ui_data = {}
    vitality_source = get_nested_value(profile_data, "vitality_information", {})
    
    if vitality_source.get("status") is not None:
        vitality_ui_data["Vitality Status"] = vitality_source["status"]

    points_renames = {
        "current_year": "Current Year Points",
        "goal_for_diamond": "Points for Diamond",
        "weekly_active_rewards_streak": "Weekly Active Rewards Streak"
    }
    points_data = process_section(get_nested_value(vitality_source, "points", {}), points_renames)
    vitality_ui_data.update(points_data)

    health_checks_renames = {
        "last_vitality_health_check": "Last Vitality Health Check",
        "weight": "Weight (kg)", "height": "Height (cm)", "bmi": "BMI",
        "blood_pressure": "Blood Pressure", "glucose": "Glucose", "LDL_cholesterol": "LDL Cholesterol"
    }
    health_checks_data = process_section(get_nested_value(vitality_source, "health_checks", {}), health_checks_renames)
    vitality_ui_data.update(health_checks_data)

    if vitality_ui_data:
        ui_profile["Vitality Health Summary"] = vitality_ui_data
        
    return ui_profile


# -------------------------------------------------#
# Prepare Nutrition_Tracking Info for Display
# -------------------------------------------------#

async def prepare_nutrition_tracking_update(profile_data: dict) -> dict:
    """
    Prepares the nutrition tracking data structure for the client based on the user profile.
    """
    if not profile_data:
        return {}

    tracking_update = {}

    # Get the daily_tracking_summary, default to an empty dict if not found
    summary = profile_data.get("daily_tracking_summary", {})
    energy_quota_data = summary.get("energy_quota", {})
    tracking_details_data = summary.get("tracking_details", {})

    # 1. Daily Energy Quota
    # UI expects: "Total", "Baseline", "Exercise" with kJ units
    tracking_update["Daily Energy Quota"] = {
        "Total": f"{energy_quota_data.get('total_kj'):,}" if energy_quota_data.get('total_kj') is not None else "N/A",
        "Baseline": f"{energy_quota_data.get('baseline_kj'):,}" if energy_quota_data.get('baseline_kj') is not None else "N/A", # Assuming this is BMR + base activity
        "Exercise": f"{energy_quota_data.get('exercise_kj'):,}" if energy_quota_data.get('exercise_kj') is not None else "0" # Placeholder for now
    }
    # Add units if not already part of the string and UI expects it, e.g. " kJ"
    for key in ["Total", "Baseline", "Exercise"]:
        if tracking_update["Daily Energy Quota"][key] != "N/A" and tracking_update["Daily Energy Quota"][key] != "0":
             tracking_update["Daily Energy Quota"][key] += " kJ"


    # 2. Daily Tracking
    # UI expects: "Energy", "Protein", "Fat", "Carbs", "Fiber"
    # Each with: "consumed"/"consumed_g", "target"/"target_g", "unit", "percentage"
    dt_energy = tracking_details_data.get("energy", {})
    dt_protein = tracking_details_data.get("protein", {})
    dt_fat = tracking_details_data.get("fat", {})
    dt_carbs = tracking_details_data.get("carbs", {})
    dt_fiber = tracking_details_data.get("fiber", {})

    daily_tracking_for_ui = {}
    if summary.get("date"): # Only populate if summary has a date (meaning it's initialized)
        daily_tracking_for_ui["Energy"] = {
            "consumed": f"{dt_energy.get('consumed_kj', 0):,}",
            "target": f"{dt_energy.get('target_kj', 0):,}" if dt_energy.get('target_kj') is not None else "N/A",
            "unit": dt_energy.get("unit", "kJ"),
            "percentage": dt_energy.get('percentage', 0)
        }
        daily_tracking_for_ui["Protein"] = {
            "consumed_g": dt_protein.get('consumed_g', 0),
            "target_g": dt_protein.get('target_g') if dt_protein.get('target_g') is not None else "N/A",
            # "unit": dt_protein.get("unit", "g"), # UI seems to expect unit in text like '...0/0g'
            "percentage": dt_protein.get('percentage', 0)
        }
        daily_tracking_for_ui["Fat"] = {
            "consumed_g": dt_fat.get('consumed_g', 0),
            "target_g": dt_fat.get('target_g') if dt_fat.get('target_g') is not None else "N/A",
            "percentage": dt_fat.get('percentage', 0)
        }
        daily_tracking_for_ui["Carbs"] = {
            "consumed_g": dt_carbs.get('consumed_g', 0),
            "target_g": dt_carbs.get('target_g') if dt_carbs.get('target_g') is not None else "N/A",
            "percentage": dt_carbs.get('percentage', 0)
        }
        daily_tracking_for_ui["Fiber"] = {
            "consumed_g": dt_fiber.get('consumed_g', 0),
            "target_g": dt_fiber.get('target_g') if dt_fiber.get('target_g') is not None else "N/A",
            "percentage": dt_fiber.get('percentage', 0)
        }
    tracking_update["Daily Tracking"] = daily_tracking_for_ui

    # 3. Logged Meals (from daily_nutrition_log)
    logged_meals_for_ui = []
    daily_log = profile_data.get("daily_nutrition_log", [])
    for logged_item in reversed(daily_log): # Show recent first
        # Assuming photo_log is the primary source for these visual meal cards
        if logged_item.get("source") == "photo_log": 
            meal_for_ui = {
                "description": logged_item.get("description", "Logged Meal"),
                "image_url": logged_item.get("image_url"), 
                "nutrition": logged_item.get("nutrition"), 
                "items": logged_item.get("items") 
            }
            logged_meals_for_ui.append(meal_for_ui)
    tracking_update["Logged Meals"] = logged_meals_for_ui
    
    logger.debug(f"Prepared nutrition tracking update for client: {json.dumps(tracking_update, indent=2)}")
    return tracking_update
