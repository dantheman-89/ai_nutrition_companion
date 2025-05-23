/*
 * UI Test Data for the Weekly Review Panel
 * ------------------------------------------
 *
 * How to use:
 * 1. Ensure your application is running in the browser.
 * 2. Open the browser's developer console (usually F12).
 * 3. Make sure the `testUpdateWeeklyReviewDisplay` function is exposed globally
 *    (e.g., `window.testUpdateWeeklyReviewDisplay = updateWeeklyReviewDisplay;` in ui.js,
 *    preferably within a DEBUG block).
 * 4. Copy one of the `testData_...` objects below.
 * 5. In the console, type `testUpdateWeeklyReviewDisplay(` then paste the copied data object,
 *    and finally add the closing parenthesis `);`. For example:
 * 6. Press Enter to execute.
 * 7. Observe the "Weekly Review" panel in the UI and check the console for any errors or debug logs.
 *
 * Each `testData_...` object below represents a specific scenario.
 * Remember to wrap the data object with `{ payload: ... }` when calling the function.
 */

// --- Test Data 1: Initial/Empty State ---
// Verifies that the panel correctly shows the placeholder text.
// Usage: testUpdateWeeklyReviewDisplay({});
const testData_InitialState_Usage = "testUpdateWeeklyReviewDisplay({});";


// --- Test Data 2: Typical Data (Energy Over, Mixed Macros) ---
// Tests the main display logic with data similar to the `weekly_summary.json` example.
// Usage: testUpdateWeeklyReviewDisplay({ payload: testData_Typical });
const testData_Typical = {
  "weekly_review_summary": {
    "period_label": "Last 7 Days",
    "total_energy": { "target_kj": 56091, "actual_kj": 51000 },
    "macronutrients_summary": [
      { "name": "Protein", "target_g": 924, "actual_g": 906 },
      { "name": "Carb", "target_g": 1568, "actual_g": 2025 },
      { "name": "Fat", "target_g": 371, "actual_g": 400 },
      { "name": "Fibre", "target_g": 161, "actual_g": 129 }
    ]
  },
  "daily_energy_breakdown": [
    { "day_label": "MON", "target_kj": 8013, "actual_kj": 9515 },
    { "day_label": "TUE", "target_kj": 8013, "actual_kj": 9317 },
    { "day_label": "WED", "target_kj": 8013, "actual_kj": 9013 },
    { "day_label": "THU", "target_kj": 8013, "actual_kj": 8720 },
    { "day_label": "FRI", "target_kj": 8013, "actual_kj": 8415 },
    { "day_label": "SAT", "target_kj": 8013, "actual_kj": 8105 },
    { "day_label": "SUN", "target_kj": 8013, "actual_kj": 7815 }
  ]
};

// testUpdateWeeklyReviewDisplay({});
testUpdateWeeklyReviewDisplay({payload: testData_Typical});

// Expected: Energy ring ~110% (orange/red), macros and daily bars reflect data.


// --- Test Data 3: Energy Under Target, Fibre Good ---
// Verifies display when energy is under target and fibre intake is good.
// Usage: testUpdateWeeklyReviewDisplay({ payload: testData_EnergyUnderFibreGood });
const testData_EnergyUnderFibreGood = {
  "weekly_review_summary": {
    "period_label": "Last 7 Days",
    "total_energy": { "target_kj": 56000, "actual_kj": 50000 },
    "macronutrients_summary": [
      { "name": "Protein", "target_g": 900, "actual_g": 850 },
      { "name": "Carb", "target_g": 1500, "actual_g": 1400 },
      { "name": "Fat", "target_g": 350, "actual_g": 330 },
      { "name": "Fibre", "target_g": 160, "actual_g": 180 } // Fibre over 100%
    ]
  },
  "daily_energy_breakdown": [
    { "day_label": "MON", "target_kj": 8000, "actual_kj": 7000 },
    { "day_label": "TUE", "target_kj": 8000, "actual_kj": 7200 },
    { "day_label": "WED", "target_kj": 8000, "actual_kj": 7100 },
    { "day_label": "THU", "target_kj": 8000, "actual_kj": 7300 },
    { "day_label": "FRI", "target_kj": 8000, "actual_kj": 7000 },
    { "day_label": "SAT", "target_kj": 8000, "actual_kj": 7400 },
    { "day_label": "SUN", "target_kj": 8000, "actual_kj": 7000 }
  ]
};
// Expected: Energy ring <100% (green), Fibre bar >100% (green).


// --- Test Data 4: Energy Significantly Over Target ---
// Verifies display for significant energy overage.
// Usage: testUpdateWeeklyReviewDisplay({ payload: testData_EnergyVeryOver });
const testData_EnergyVeryOver = {
  "weekly_review_summary": {
    "period_label": "Last 7 Days",
    "total_energy": { "target_kj": 56000, "actual_kj": 70000 }, // Significantly over
    "macronutrients_summary": [
      { "name": "Protein", "target_g": 900, "actual_g": 950 },
      { "name": "Carb", "target_g": 1500, "actual_g": 1800 }, // Over
      { "name": "Fat", "target_g": 350, "actual_g": 450 },   // Over
      { "name": "Fibre", "target_g": 160, "actual_g": 100 }  // Under
    ]
  },
  "daily_energy_breakdown": [
    { "day_label": "MON", "target_kj": 8000, "actual_kj": 10000 },
    { "day_label": "TUE", "target_kj": 8000, "actual_kj": 10000 },
    { "day_label": "WED", "target_kj": 8000, "actual_kj": 10000 },
    { "day_label": "THU", "target_kj": 8000, "actual_kj": 10000 },
    { "day_label": "FRI", "target_kj": 8000, "actual_kj": 10000 },
    { "day_label": "SAT", "target_kj": 8000, "actual_kj": 10000 },
    { "day_label": "SUN", "target_kj": 8000, "actual_kj": 10000 }
  ]
};
// Expected: Energy ring >110% (red), Carb/Fat bars >110% (red).


// --- Test Data 5: Minimal Data (Only Total Energy) ---
// Tests graceful degradation if parts of the data (macros, daily breakdown) are missing.
// Usage: testUpdateWeeklyReviewDisplay({ payload: testData_Minimal });
const testData_Minimal = {
  "weekly_review_summary": {
    "period_label": "Last 7 Days",
    "total_energy": { "target_kj": 56000, "actual_kj": 60000 }
  }
};
// Expected: Energy ring displays, macro/daily sections empty, no errors.


// --- Test Data 6: Data with Zero Targets ---
// Tests behavior when targets are zero (e.g., new user).
// Usage: testUpdateWeeklyReviewDisplay({ payload: testData_ZeroTargets });
const testData_ZeroTargets = {
  "weekly_review_summary": {
    "period_label": "Last 7 Days",
    "total_energy": { "target_kj": 0, "actual_kj": 5000 },
    "macronutrients_summary": [
      { "name": "Protein", "target_g": 0, "actual_g": 50 },
      { "name": "Fibre", "target_g": 0, "actual_g": 10 }
    ]
  },
  "daily_energy_breakdown": [
    { "day_label": "MON", "target_kj": 0, "actual_kj": 1000 },
    { "day_label": "TUE", "target_kj": 0, "actual_kj": 700 }
  ]
};
// Expected: Displays based on actuals, no division by zero errors.

/*
Example of how to use in console:

1. Copy one of the data objects above, for example, testData_Typical:
   {
     "weekly_review_summary": { ... },
     "daily_energy_breakdown": [ ... ]
   }

2. In the browser console, type:
   testUpdateWeeklyReviewDisplay({ payload: PASTE COPIED DATA HERE 


//    It should look like:
   testUpdateWeeklyReviewDisplay({ payload: {
     "weekly_review_summary": {
       "period_label": "Last 7 Days",
       "total_energy": { "target_kj": 56091, "actual_kj": 61700 },
       "macronutrients_summary": [
         { "name": "Protein", "target_g": 924, "actual_g": 906 },
         { "name": "Carb", "target_g": 1568, "actual_g": 1725 },
         { "name": "Fat", "target_g": 371, "actual_g": 408 },
         { "name": "Fibre", "target_g": 161, "actual_g": 129 }
       ]
     },
     "daily_energy_breakdown": [
       { "day_label": "MON", "target_kj": 8013, "actual_kj": 8815 },
       { "day_label": "TUE", "target_kj": 8013, "actual_kj": 8817 },
       { "day_label": "WED", "target_kj": 8013, "actual_kj": 8813 },
       { "day_label": "THU", "target_kj": 8013, "actual_kj": 8820 },
       { "day_label": "FRI", "target_kj": 8013, "actual_kj": 8815 },
       { "day_label": "SAT", "target_kj": 8013, "actual_kj": 8805 },
       { "day_label": "SUN", "target_kj": 8013, "actual_kj": 8815 }
     ]
   }});
*/