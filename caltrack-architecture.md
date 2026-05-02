# CalTrack — Full Architecture Blueprint

**Personal AI-Powered Calorie Tracking System**
**Version 2.0 — Revised April 2026**

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Technology Stack](#3-technology-stack)
4. [Database Schema](#4-database-schema)
5. [Nutrition Data Strategy](#5-nutrition-data-strategy)
6. [Core Flow: Meal Logging](#6-core-flow-meal-logging)
7. [Personal Food Learning Engine](#7-personal-food-learning-engine)
8. [BMR / TDEE Auto-Calibration](#8-bmr--tdee-auto-calibration)
9. [Exercise Integration](#9-exercise-integration)
10. [AI Coach — Weekly Analysis](#10-ai-coach--weekly-analysis)
11. [Telegram Bot Interface](#11-telegram-bot-interface)
12. [Dashboard (Analytics UI)](#12-dashboard-analytics-ui)
13. [AI Prompts — Full Specifications](#13-ai-prompts--full-specifications)
14. [Privacy & Security](#14-privacy--security)
15. [Development Roadmap](#15-development-roadmap)
16. [Cost Estimate](#16-cost-estimate)

---

## 1. Project Overview

### What Is CalTrack?

CalTrack is a single-user, privacy-first calorie tracking system. The user photographs meals and sends them to a Telegram bot. An AI vision model identifies the food items, the user confirms or corrects the estimated weights, and the system logs the nutritional data. Over time, the system learns the user's eating patterns and becomes faster and more accurate.

### Design Principles

| Principle | What It Means in Practice |
|---|---|
| **Minimal friction** | Logging a meal must take < 30 seconds after the first month |
| **Accuracy over convenience** | Never trust AI weight estimates blindly; always allow manual correction |
| **Continuous improvement** | The system gets smarter by learning from corrections and usage patterns |
| **Total privacy** | Single-user system, all data behind RLS or self-hosted |
| **Honest tracking** | Show real numbers, don't sugarcoat — the user wants deficit data, not encouragement |

### What CalTrack Is NOT

- Not a social app — no sharing, no community features
- Not a meal planner (yet) — it tracks what you ate, not what you should eat
- Not a medical device — it's an estimation tool to support calorie deficit goals

---

## 2. System Architecture

### High-Level Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                         INPUT LAYER                              │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                    TELEGRAM BOT                          │    │
│  │                                                          │    │
│  │  • Send meal photo → AI identifies food                  │    │
│  │  • Confirm/correct weights via inline keyboard           │    │
│  │  • Log body weight (/weight)                             │    │
│  │  • Log water intake (/water)                             │    │
│  │  • Log manual run (/run)                                 │    │
│  │  • Request daily/weekly summary                          │    │
│  │  • Undo last entry (/undo)                               │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────┐
│                      PROCESSING LAYER                            │
│                      (Python Backend)                             │
│                                                                  │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────┐  │
│  │  VISION AI     │  │  NUTRITION     │  │  PERSONAL FOOD     │  │
│  │  (OpenRouter)  │  │  RESOLVER      │  │  LEARNING ENGINE   │  │
│  │                │  │                │  │                    │  │
│  │  Input: photo  │  │  Input: fdc_id │  │  Input: correction │  │
│  │  + food list   │  │  + weight      │  │  history           │  │
│  │                │  │                │  │                    │  │
│  │  Output: JSON  │  │  Output:       │  │  Output: suggested │  │
│  │  with fdc_ids  │  │  cal/protein/  │  │  weights + auto-   │  │
│  │  + weights     │  │  carbs/fat     │  │  approve decisions │  │
│  └────────────────┘  └────────────────┘  └────────────────────┘  │
│                                                                  │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────┐  │
│  │  BMR / TDEE    │  │  STRAVA /      │  │  AI COACH          │  │
│  │  CALIBRATOR    │  │  GARMIN SYNC   │  │  (OpenRouter)      │  │
│  │                │  │                │  │                    │  │
│  │  Recalculates  │  │  Auto-import   │  │  Weekly analysis   │  │
│  │  targets when  │  │  runs with     │  │  in English,       │  │
│  │  weight changes│  │  active cals   │  │  output in Hebrew  │  │
│  └────────────────┘  └────────────────┘  └────────────────────┘  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────┐
│                        DATA LAYER                                │
│                        (Supabase)                                 │
│                                                                  │
│  ┌─────────────────────────┐  ┌───────────────────────────────┐  │
│  │      PostgreSQL         │  │     Supabase Storage (S3)     │  │
│  │                         │  │                               │  │
│  │  • user_profile         │  │  • /meals/{date}/{meal_id}    │  │
│  │  • meals                │  │    Original meal photos       │  │
│  │  • meal_items           │  │                               │  │
│  │  • personal_foods       │  │                               │  │
│  │  • personal_food_logs   │  │                               │  │
│  │  • ai_corrections       │  │                               │  │
│  │  • weight_log           │  │                               │  │
│  │  • water_log            │  │                               │  │
│  │  • runs                 │  │                               │  │
│  │  • daily_summary        │  │                               │  │
│  │  • calibration_log      │  │                               │  │
│  │  • usda_foundation      │  │                               │  │
│  └─────────────────────────┘  └───────────────────────────────┘  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────┐
│                       OUTPUT LAYER                               │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  TELEGRAM (inline summaries)                             │    │
│  │  • Post-meal calorie update                              │    │
│  │  • Daily summary on demand                               │    │
│  │  • Weekly AI Coach report                                │    │
│  │  • Calibration alerts when targets change                │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  DASHBOARD (Streamlit → Next.js)                         │    │
│  │  • Daily/weekly/monthly calorie trends                   │    │
│  │  • Macro breakdown charts (protein/carbs/fat)            │    │
│  │  • Weight trend graph                                    │    │
│  │  • Drill-down: each meal with photo + item breakdown     │    │
│  │  • Calories in vs. calories out comparison               │    │
│  │  • AI Coach weekly report (full version)                 │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

### Data Flow Summary

```
Photo → Telegram Bot → OpenRouter Vision API → JSON (items + fdc_ids + weights)
  → Check personal_food_logs for known items
    → Known + high confidence → auto-approve with historical weight
    → Unknown or low confidence → present inline keyboard for correction
  → Resolve nutrition via local USDA Foundation Foods table
  → Save to meals + meal_items
  → Update personal_foods + personal_food_logs
  → If corrected → save to ai_corrections
  → Update daily_summary
  → Return inline confirmation with remaining calories
```

---

## 3. Technology Stack

| Layer | Technology | Why This Choice |
|---|---|---|
| **User Interface** | Telegram Bot (`python-telegram-bot` v20+) | Zero friction — already on phone, supports inline keyboards, camera access, private by default |
| **Backend Runtime** | Python 3.11+ | Best ecosystem for AI APIs, data processing, existing Strava/Garmin code |
| **Vision AI** | OpenRouter API → GPT-4o / Claude Sonnet | Best vision models for food identification; OpenRouter allows model switching |
| **Nutrition Data** | USDA Foundation Foods (local PostgreSQL table) | ~2,000 base ingredients, no API latency, no search ambiguity |
| **Nutrition Data (packaged)** | Open Food Facts API | Barcode scanning for packaged products (Stage 3) |
| **Database** | Supabase (PostgreSQL + Storage + Auth) | Managed Postgres, built-in file storage for photos, RLS for privacy, generous free tier |
| **Exercise Data** | Strava API (primary) / Garmin API (fallback) | Auto-import runs with active calories; existing integration code available |
| **AI Coach** | OpenRouter API → Claude / o3-mini | Weekly dietary analysis and recommendations |
| **Analytics Dashboard** | Streamlit (Stage 1) → Next.js (Stage 3+) | Streamlit for fast MVP; Next.js for production-grade UI later |
| **Hosting** | Railway / Fly.io / local machine | Bot needs to run 24/7; Railway free tier or local Docker |

---

## 4. Database Schema

### 4.1 `user_profile`

Stores user biometrics, goals, and preferences. Single row (single-user system).

```sql
CREATE TABLE user_profile (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Biometrics
    height_cm INTEGER NOT NULL,
    current_weight_kg DECIMAL(5,2) NOT NULL,
    age INTEGER NOT NULL,
    sex TEXT NOT NULL CHECK (sex IN ('male', 'female')),

    -- Goals
    target_weight_kg DECIMAL(5,2) NOT NULL,
    target_daily_calories INTEGER NOT NULL,
    target_weekly_deficit_kg DECIMAL(3,2) DEFAULT 0.5,
        -- 0.5 kg/week = ~550 cal/day deficit

    -- Calculated fields (updated by calibration)
    bmr INTEGER,
        -- Mifflin-St Jeor: 10×weight + 6.25×height - 5×age - 161 (male: +5)
    tdee INTEGER,
        -- BMR × activity_factor
    activity_factor DECIMAL(3,2) DEFAULT 1.55,
        -- 1.2 sedentary | 1.375 light | 1.55 moderate | 1.725 active
    last_calibration_date DATE,

    -- Preferences
    food_preferences JSONB DEFAULT '{}'::JSONB,
        -- Example: {
        --   "likes": ["grilled meats", "salads", "rice dishes"],
        --   "dislikes": ["fish", "mushrooms"],
        --   "allergies": [],
        --   "cooking_style": "simple, quick meals"
        -- }

    -- Telegram
    telegram_chat_id BIGINT UNIQUE NOT NULL,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 4.2 `usda_foundation` (local nutrition lookup)

Pre-loaded from USDA Foundation Foods dataset. ~2,000 rows of base ingredients.

```sql
CREATE TABLE usda_foundation (
    fdc_id INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
        -- e.g., "Chicken, breast, meat only, cooked, grilled"
    food_category TEXT,
        -- e.g., "Poultry Products"
    calories_per_100g DECIMAL(7,2),
    protein_per_100g DECIMAL(6,2),
    carbs_per_100g DECIMAL(6,2),
    fat_per_100g DECIMAL(6,2),
    fiber_per_100g DECIMAL(6,2),
    sodium_mg_per_100g DECIMAL(7,2),
    sugar_per_100g DECIMAL(6,2),

    -- For embedding/search
    search_keywords TEXT[],
        -- e.g., {"chicken", "breast", "grilled", "poultry"}
    embedding VECTOR(384)
        -- Optional: for semantic search if needed
);

-- Index for fast text search
CREATE INDEX idx_usda_search ON usda_foundation USING GIN (search_keywords);
```

### 4.3 `meals`

One row per eating event (breakfast, lunch, dinner, snack).

```sql
CREATE TABLE meals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profile(id) NOT NULL,

    meal_type TEXT NOT NULL CHECK (meal_type IN (
        'breakfast', 'lunch', 'dinner', 'snack'
    )),
    eaten_at TIMESTAMPTZ DEFAULT NOW(),

    -- Photo
    photo_path TEXT,
        -- Supabase Storage path: meals/{YYYY-MM-DD}/{meal_id}.jpg

    -- Aggregated nutrition (sum of meal_items)
    total_calories INTEGER DEFAULT 0,
    total_protein_g DECIMAL(6,2) DEFAULT 0,
    total_carbs_g DECIMAL(6,2) DEFAULT 0,
    total_fat_g DECIMAL(6,2) DEFAULT 0,
    total_fiber_g DECIMAL(6,2) DEFAULT 0,

    -- AI metadata
    ai_model_used TEXT,
        -- e.g., "gpt-4o-2024-08-06"
    ai_raw_response JSONB,
        -- Full AI response for debugging
    processing_time_ms INTEGER,

    -- Status
    status TEXT DEFAULT 'confirmed' CHECK (status IN (
        'pending', 'confirmed', 'cancelled'
    )),
    notes TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_meals_date ON meals (eaten_at DESC);
CREATE INDEX idx_meals_user ON meals (user_id, eaten_at DESC);
```

### 4.4 `meal_items`

Individual food items within a meal. Each row = one ingredient.

```sql
CREATE TABLE meal_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meal_id UUID REFERENCES meals(id) ON DELETE CASCADE NOT NULL,

    -- Identification
    ingredient_name TEXT NOT NULL,
        -- English name from AI, e.g., "grilled chicken breast"
    ingredient_name_he TEXT,
        -- Hebrew name for display, e.g., "חזה עוף צלוי"
    fdc_id INTEGER REFERENCES usda_foundation(fdc_id),
        -- Direct link to USDA Foundation Foods

    -- Weight
    weight_grams INTEGER NOT NULL,
    weight_source TEXT NOT NULL CHECK (weight_source IN (
        'ai_estimate',        -- Raw AI estimate, not yet confirmed
        'user_confirmed',     -- User accepted AI estimate as-is
        'user_corrected',     -- User changed the weight
        'personal_db_auto',   -- Auto-approved from personal_foods history
        'barcode_lookup'      -- From Open Food Facts (future)
    )),
    ai_estimated_grams INTEGER,
        -- Always store original AI estimate for learning

    -- Nutrition (calculated from fdc_id × weight)
    calories INTEGER,
    protein_g DECIMAL(6,2),
    carbs_g DECIMAL(6,2),
    fat_g DECIMAL(6,2),
    fiber_g DECIMAL(6,2),

    -- AI confidence
    ai_confidence DECIMAL(3,2),
        -- 0.00 - 1.00, from the vision model

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_meal_items_meal ON meal_items (meal_id);
CREATE INDEX idx_meal_items_fdc ON meal_items (fdc_id);
```

### 4.5 `personal_foods`

Master table for foods the user has logged. Tracks aggregate stats.

```sql
CREATE TABLE personal_foods (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identity
    ingredient_name TEXT NOT NULL,
    fdc_id INTEGER REFERENCES usda_foundation(fdc_id),

    -- Usage stats (aggregated across all meal types)
    total_times_logged INTEGER DEFAULT 1,
    total_times_corrected INTEGER DEFAULT 0,
    first_logged_at TIMESTAMPTZ DEFAULT NOW(),
    last_logged_at TIMESTAMPTZ DEFAULT NOW(),

    -- Cached nutrition per 100g (from USDA)
    calories_per_100g DECIMAL(7,2),
    protein_per_100g DECIMAL(6,2),
    carbs_per_100g DECIMAL(6,2),
    fat_per_100g DECIMAL(6,2),

    UNIQUE(ingredient_name)
);
```

### 4.6 `personal_food_logs`

Per-usage history for each food. This replaces the flawed "average weight" approach.
Instead of storing one average, we store every confirmed weight so the system can
offer context-aware suggestions (last N weights for same meal type).

```sql
CREATE TABLE personal_food_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    personal_food_id UUID REFERENCES personal_foods(id) ON DELETE CASCADE,
    meal_id UUID REFERENCES meals(id) ON DELETE CASCADE,

    -- Context
    meal_type TEXT NOT NULL,
        -- breakfast / lunch / dinner / snack
    weight_grams INTEGER NOT NULL,
    weight_source TEXT NOT NULL,
        -- Same options as meal_items.weight_source

    -- What AI estimated vs. what user confirmed
    ai_estimated_grams INTEGER,
    was_corrected BOOLEAN DEFAULT FALSE,

    logged_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_pfl_food ON personal_food_logs (personal_food_id, meal_type);
CREATE INDEX idx_pfl_recent ON personal_food_logs (personal_food_id, logged_at DESC);
```

**How suggestions are generated from this table:**

```sql
-- Get last 5 confirmed weights for "white rice" at "lunch"
SELECT weight_grams
FROM personal_food_logs
WHERE personal_food_id = :food_id
  AND meal_type = 'lunch'
ORDER BY logged_at DESC
LIMIT 5;

-- Returns: [200, 200, 180, 200, 150]
-- → Offer inline keyboard: [150g] [180g] [200g] [✏️ manual]
-- → Most common = 200g, pre-select it
```

### 4.7 `ai_corrections`

Every time the user corrects an AI estimate, log it here. Used to build few-shot
examples for prompt improvement.

```sql
CREATE TABLE ai_corrections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meal_item_id UUID REFERENCES meal_items(id),

    ingredient_name TEXT NOT NULL,
    meal_type TEXT NOT NULL,
    ai_estimated_grams INTEGER NOT NULL,
    user_corrected_grams INTEGER NOT NULL,
    correction_delta INTEGER GENERATED ALWAYS AS
        (user_corrected_grams - ai_estimated_grams) STORED,
        -- Negative = AI overestimated, Positive = AI underestimated

    corrected_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_corrections_ingredient ON ai_corrections (ingredient_name);
```

### 4.8 `weight_log`

```sql
CREATE TABLE weight_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profile(id),
    weight_kg DECIMAL(5,2) NOT NULL,
    measured_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_weight_date ON weight_log (measured_at DESC);
```

### 4.9 `water_log`

```sql
CREATE TABLE water_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profile(id),
    amount_ml INTEGER NOT NULL,
    logged_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 4.10 `runs`

```sql
CREATE TABLE runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profile(id),

    -- Core data
    distance_km DECIMAL(5,2),
    duration_minutes INTEGER,
    avg_pace_sec_per_km INTEGER,
        -- Stored as seconds for easy math; display as "5:30/km"
    avg_heart_rate INTEGER,
    max_heart_rate INTEGER,
    calories_burned INTEGER,
    elevation_gain_m INTEGER,

    -- Source
    source TEXT NOT NULL CHECK (source IN ('strava', 'garmin', 'manual')),
    external_id TEXT,
        -- Strava activity ID or Garmin activity ID
    external_url TEXT,
        -- Link back to Strava/Garmin activity

    run_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Prevent duplicate imports
    UNIQUE(source, external_id)
);

CREATE INDEX idx_runs_date ON runs (run_date DESC);
```

### 4.11 `daily_summary`

Materialized view or table, refreshed after each meal/run/weight entry.

```sql
CREATE TABLE daily_summary (
    date DATE PRIMARY KEY,
    user_id UUID REFERENCES user_profile(id),

    -- Intake
    total_calories_in INTEGER DEFAULT 0,
    total_protein_g DECIMAL(6,2) DEFAULT 0,
    total_carbs_g DECIMAL(6,2) DEFAULT 0,
    total_fat_g DECIMAL(6,2) DEFAULT 0,
    total_fiber_g DECIMAL(6,2) DEFAULT 0,
    meal_count INTEGER DEFAULT 0,

    -- Output
    calories_burned_exercise INTEGER DEFAULT 0,
        -- Sum from runs table
    bmr_calories INTEGER,
        -- From user_profile at that date
    tdee_calories INTEGER,
        -- bmr × activity_factor

    -- Balance
    net_calories INTEGER GENERATED ALWAYS AS
        (total_calories_in - calories_burned_exercise) STORED,
    target_calories INTEGER,
    calorie_surplus_deficit INTEGER GENERATED ALWAYS AS
        (total_calories_in - calories_burned_exercise - target_calories) STORED,
        -- Negative = deficit (good), Positive = surplus

    -- Body
    weight_kg DECIMAL(5,2),
    water_ml INTEGER DEFAULT 0,

    -- Meta
    auto_approved_meal_pct DECIMAL(3,2),
        -- What % of meals were auto-approved (learning metric)

    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 4.12 `calibration_log`

Tracks BMR/TDEE recalculations over time.

```sql
CREATE TABLE calibration_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Before
    previous_weight_kg DECIMAL(5,2),
    previous_bmr INTEGER,
    previous_tdee INTEGER,
    previous_target_calories INTEGER,

    -- After
    new_weight_kg DECIMAL(5,2),
    new_bmr INTEGER,
    new_tdee INTEGER,
    new_target_calories INTEGER,

    -- Context
    weight_trend_7d DECIMAL(4,2),
        -- Average weight change over past 7 days
    trigger TEXT NOT NULL CHECK (trigger IN (
        'weekly_auto',     -- Automatic weekly recalibration
        'manual',          -- User requested recalibration
        'weight_milestone' -- Weight crossed a 2kg threshold
    )),

    calibrated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 5. Nutrition Data Strategy

### The Problem with USDA API

Searching the full USDA FoodData Central API for "chicken breast" returns hundreds of
results including commercial brands, raw vs. cooked variants, and products from different
countries. Picking the wrong entry can mean a 100+ calorie error per item.

### The Solution: Local Foundation Foods Table

1. **Download** the USDA Foundation Foods dataset (CSV/JSON from
   https://fdc.nal.usda.gov/download-datasets)
2. **Filter** to Foundation Foods only (~2,000 base ingredients — no brands, no
   commercial products)
3. **Load** into the `usda_foundation` table in Supabase
4. **Provide the food list to the Vision AI** so it returns `fdc_id` directly
   instead of free-text names

### How It Works in Practice

```
Step 1: On bot startup, load all usda_foundation entries into memory
        as a lookup dictionary: {fdc_id: description, ...}

Step 2: Build a condensed food list for the Vision AI prompt:
        "167512: Chicken, breast, cooked, grilled
         168880: Rice, white, long-grain, cooked
         170148: Egg, whole, hard-boiled
         ..."
        (~2,000 entries ≈ ~30K tokens — fits in context)

Step 3: Vision AI prompt includes this list and instructions:
        "Match each identified food to the closest fdc_id from the
         provided list. Return the fdc_id, not a text description."

Step 4: Backend receives fdc_id → direct lookup → exact nutrition values
        No search ambiguity, no API latency.
```

### Handling Items Not in Foundation Foods

If the AI identifies a food that doesn't match any Foundation Foods entry (e.g., a
specific brand or a complex dish), it should:

1. Return `fdc_id: null` with the text description
2. Backend falls back to asking the AI itself for estimated nutrition per 100g
3. Flag the item for user review

### Food List Size Optimization

If ~30K tokens is too large for every prompt:

- **Option A:** Pre-filter to top 500 most common foods (covers ~90% of meals)
- **Option B:** Use embedding search — encode the AI's text description, find nearest
  USDA entry by cosine similarity, return top 3 matches for user selection
- **Option C:** Categorize by food group — send only relevant categories based on
  initial rough classification ("this looks like a meat dish" → send only Protein entries)

**Recommended for MVP:** Option A (top 500 foods) — simple, fast, sufficient.

---

## 6. Core Flow: Meal Logging

### Sequence Diagram

```
User                    Telegram Bot              OpenRouter           Supabase
 │                          │                        │                    │
 │── Send photo ──────────▶│                        │                    │
 │                          │                        │                    │
 │                          │── Upload photo ──────────────────────────▶│
 │                          │◀── photo_path ──────────────────────────│
 │                          │                        │                    │
 │                          │── Send photo +         │                    │
 │                          │   food list +          │                    │
 │                          │   personal history ──▶│                    │
 │                          │                        │                    │
 │                          │◀── JSON response ─────│                    │
 │                          │   [{fdc_id, name,      │                    │
 │                          │     weight, confidence}]│                   │
 │                          │                        │                    │
 │                          │── Check personal_food_logs ──────────────▶│
 │                          │◀── historical weights ──────────────────│
 │                          │                        │                    │
 │                          │── Resolve nutrition    │                    │
 │                          │   from usda_foundation │                    │
 │                          │   (local lookup)       │                    │
 │                          │                        │                    │
 │◀── Inline keyboard ─────│                        │                    │
 │   with items + weights   │                        │                    │
 │   + nutrition summary    │                        │                    │
 │                          │                        │                    │
 │── Confirm / Correct ───▶│                        │                    │
 │                          │                        │                    │
 │                          │── Save meal + items ─────────────────────▶│
 │                          │── Update personal_foods ─────────────────▶│
 │                          │── Update daily_summary ──────────────────▶│
 │                          │── Save corrections (if any) ─────────────▶│
 │                          │                        │                    │
 │◀── "✅ Saved! Today:    │                        │                    │
 │     1,340/2,000 kcal     │                        │                    │
 │     (660 remaining)"     │                        │                    │
```

### Meal Type Detection

The bot should auto-detect meal type based on time of day (user's timezone):

| Time | Default Meal Type |
|---|---|
| 06:00 – 10:59 | breakfast |
| 11:00 – 14:59 | lunch |
| 15:00 – 17:59 | snack |
| 18:00 – 22:59 | dinner |
| 23:00 – 05:59 | snack |

User can override with a reply or inline button.

---

## 7. Personal Food Learning Engine

### Purpose

Eliminate repetitive corrections. After logging "white rice at lunch" 10 times and
confirming it's always ~200g, the system should auto-suggest 200g without asking.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  DECISION FLOW PER ITEM                     │
│                                                             │
│  AI identifies: "white rice, 180g, confidence: 0.75"        │
│                          │                                  │
│                          ▼                                  │
│  ┌─────────────────────────────────────────┐                │
│  │ Lookup in personal_foods:               │                │
│  │ Does "white rice" exist with >5 logs?   │                │
│  └─────────┬────────────────────┬──────────┘                │
│            │                    │                           │
│          YES                   NO                           │
│            │                    │                           │
│            ▼                    ▼                           │
│  ┌──────────────────┐  ┌──────────────────┐                 │
│  │ Query last 5      │  │ Use AI estimate  │                 │
│  │ weights for this  │  │ Present full     │                 │
│  │ item + meal_type  │  │ inline keyboard  │                 │
│  │ from              │  │ for correction   │                 │
│  │ personal_food_logs│  │                  │                 │
│  └────────┬─────────┘  └──────────────────┘                 │
│           │                                                 │
│           ▼                                                 │
│  ┌──────────────────────────────────────┐                   │
│  │ Analyze history:                     │                   │
│  │                                      │                   │
│  │ Last 5 weights: [200, 200, 180, 200] │                   │
│  │ Mode (most common): 200g             │                   │
│  │ Std deviation: 10g                   │                   │
│  │ Times corrected: 1/10 (10%)          │                   │
│  │                                      │                   │
│  │ → Low variance + low correction rate │                   │
│  │ → AUTO-APPROVE at 200g               │                   │
│  └──────────────────────────────────────┘                   │
│                                                             │
│  AUTO-APPROVE CRITERIA:                                     │
│  • total_times_logged >= 5 for this meal_type               │
│  • correction_rate < 20% (corrected / logged)               │
│  • weight std_dev < 30g                                     │
│  • All 3 conditions must be true simultaneously             │
│                                                             │
│  If ANY condition fails → present inline keyboard           │
└─────────────────────────────────────────────────────────────┘
```

### Inline Keyboard Weight Suggestions

When manual confirmation is needed, the keyboard offers smart options:

```python
def get_weight_suggestions(food_id: str, meal_type: str, ai_estimate: int) -> list[int]:
    """
    Returns 3-4 weight options for inline keyboard.
    Priority: historical weights > AI estimate > standard portions.
    """

    # Get last 5 confirmed weights for this food + meal type
    history = query("""
        SELECT weight_grams FROM personal_food_logs
        WHERE personal_food_id = :food_id AND meal_type = :meal_type
        ORDER BY logged_at DESC LIMIT 5
    """)

    if len(history) >= 3:
        # Use historical values: most common, min, max
        weights = [h.weight_grams for h in history]
        suggestions = sorted(set([
            min(weights),
            statistics.mode(weights),
            max(weights)
        ]))
    else:
        # Not enough history — offer AI estimate ± 25%
        suggestions = sorted(set([
            round_to_10(ai_estimate * 0.75),
            round_to_10(ai_estimate),
            round_to_10(ai_estimate * 1.25)
        ]))

    return suggestions  # Always add "✏️ manual" button alongside
```

---

## 8. BMR / TDEE Auto-Calibration

### Why This Matters

As the user loses weight, their BMR decreases. If the calorie target stays fixed,
the deficit shrinks and eventually disappears (plateau). The system must automatically
adjust.

### Calculation Formula

Using **Mifflin-St Jeor** (most accurate for overweight individuals):

```
Male:   BMR = (10 × weight_kg) + (6.25 × height_cm) - (5 × age) + 5
Female: BMR = (10 × weight_kg) + (6.25 × height_cm) - (5 × age) - 161

TDEE = BMR × activity_factor

Target = TDEE - deficit_calories
  where deficit_calories = target_weekly_deficit_kg × 7700 / 7
  (7700 kcal ≈ 1 kg of fat)
  (0.5 kg/week → ~550 kcal/day deficit)
```

### Calibration Triggers

```
┌────────────────────────────────────────────────────┐
│              WEEKLY CALIBRATION JOB                 │
│              (runs every Sunday)                    │
│                                                    │
│  1. Calculate 7-day weight trend:                  │
│     avg_weight_this_week vs. avg_weight_last_week  │
│                                                    │
│  2. If weight changed by > 0.3 kg:                 │
│     → Recalculate BMR with new weight              │
│     → Recalculate TDEE                             │
│     → Recalculate target_daily_calories            │
│     → Update user_profile                          │
│     → Log to calibration_log                       │
│     → Send Telegram notification:                  │
│       "📊 Weekly calibration:                      │
│        Weight trend: 87.5 → 86.8 kg (-0.7)        │
│        New BMR: 1,782 kcal                         │
│        New TDEE: 2,762 kcal                        │
│        New daily target: 2,212 → 2,195 kcal (-17) │
│        Keep it up! 💪"                              │
│                                                    │
│  3. If weight unchanged or increased:              │
│     → AI Coach addresses this in weekly report     │
│     → Consider suggesting lower activity_factor    │
│                                                    │
│  ADDITIONAL TRIGGER:                               │
│  If weight crosses a 2kg threshold (e.g., 88→86):  │
│  → Immediate recalibration + notification          │
└────────────────────────────────────────────────────┘
```

### Safety Guards

- Minimum target_daily_calories: **1,500 kcal** (male) / **1,200 kcal** (female)
- Maximum deficit: **1,000 kcal/day** (≈1 kg/week loss)
- If calculated target falls below minimum → alert user and cap at minimum
- If weight increases for 3+ consecutive weeks → suggest reviewing activity_factor

---

## 9. Exercise Integration

### Strava API Integration (Primary)

```
┌─────────────────────────────────────────────────┐
│            STRAVA SYNC FLOW                     │
│                                                 │
│  1. OAuth2 authentication (one-time setup)      │
│     → Store access_token + refresh_token        │
│     → Auto-refresh when expired                 │
│                                                 │
│  2. Webhook subscription (preferred):           │
│     Strava pushes new activity notifications    │
│     → Bot fetches activity details              │
│     → Saves to runs table                       │
│                                                 │
│  3. Fallback: Polling (every 30 min):           │
│     GET /athlete/activities?after={timestamp}   │
│     → Check for new runs not yet in DB          │
│     → Import and save                           │
│                                                 │
│  4. Data extracted per run:                     │
│     • distance (meters → km)                    │
│     • moving_time (seconds → minutes)           │
│     • average_speed → pace (sec/km)             │
│     • average_heartrate                         │
│     • total_elevation_gain                      │
│     • calories (if available from device)       │
│                                                 │
│  5. If Strava doesn't provide calories:         │
│     Calculate using MET formula:                │
│     calories = MET × weight_kg × duration_hours │
│     Running MET by pace:                        │
│       < 5:00/km → MET 11.0                     │
│       5:00-6:00 → MET 9.8                      │
│       6:00-7:00 → MET 8.3                      │
│       > 7:00/km → MET 7.0                      │
│                                                 │
│  6. After import → update daily_summary         │
│     → Send Telegram notification:               │
│     "🏃 Run imported from Strava:               │
│      5.2 km | 28:30 | 5:29/km | ❤️ 152         │
│      Burned: ~420 kcal                          │
│      Today's balance: 1,340 - 420 = 920 net"   │
└─────────────────────────────────────────────────┘
```

### Manual Run Entry (Fallback)

```
Command: /run 5.2 28:30 152

Parsed:  distance=5.2km  duration=28:30  avg_hr=152
Calculated: pace=5:29/km  calories=~420 (MET formula)

Saved and reflected in daily summary.
```

---

## 10. AI Coach — Weekly Analysis

### Architecture

```
Every Sunday at 21:00 (user's timezone):

1. Gather data:
   - 7 days of meals + items + nutrition
   - 7 days of runs
   - 7 days of weight measurements
   - Current user_profile (targets, preferences)
   - Calibration results (if recalibrated this week)

2. Build prompt (see Section 13 for full prompt)

3. Send to OpenRouter:
   - Model: Claude Sonnet or o3-mini
   - Temperature: 0.3 (factual, consistent)
   - CRITICAL: Analysis performed in English,
     final output translated to Hebrew

4. Receive structured response

5. Send to user via Telegram (formatted message)

6. Store response in DB for dashboard display
```

### What the AI Coach Analyzes

| Analysis Area | What It Looks For |
|---|---|
| **Deficit status** | Average daily deficit across the week — on target, below, or above? |
| **Macro balance** | Protein ratio (target: ~30% of calories), fiber intake (target: 25g+/day) |
| **Timing patterns** | Late-night eating, long gaps between meals, post-run overeating |
| **Problem foods** | Recurring high-calorie, low-nutrient items |
| **Improvement trend** | Is this week better than last week? Specific metrics that improved |
| **Actionable tips** | 3 specific changes for next week, ranked by impact |
| **Recipe suggestions** | 2 recipes matching user preferences that fit the calorie target |

---

## 11. Telegram Bot Interface

### Command Reference

| Command | Action | Example |
|---|---|---|
| 📷 *Send photo* | Log a meal | Just send any food photo |
| `/weight [kg]` | Log body weight | `/weight 87.3` |
| `/water [ml]` | Log water intake | `/water 500` |
| `/run [km] [mm:ss] [hr]` | Log manual run | `/run 5.2 28:30 152` |
| `/summary` or `/s` | Today's summary | `/s` |
| `/week` or `/w` | Weekly AI Coach report | `/w` |
| `/status` | Remaining calories today | `/status` |
| `/undo` | Cancel last logged meal | `/undo` |
| `/history [n]` | Last N meals | `/history 5` |
| `/calibrate` | Force recalibration | `/calibrate` |
| `/help` | List all commands | `/help` |

### Inline Keyboard Layouts

**Meal confirmation (after photo analysis):**

```
┌────────────────────────────────────────┐
│ 🍽 Lunch — April 28, 13:15             │
│                                        │
│ 1. Grilled chicken breast              │
│    AI estimate: 150g (confidence: 82%) │
│    [100g] [150g] [200g] [✏️]           │
│                                        │
│ 2. White rice, cooked                  │
│    Auto-approved: 200g ✅ (from history)│
│                                        │
│ 3. Mixed green salad                   │
│    AI estimate: 120g (confidence: 65%) │
│    [80g] [100g] [120g] [150g] [✏️]     │
│                                        │
│ ─────────────────────                  │
│ Total: ~565 kcal                       │
│ P: 42g | C: 58g | F: 12g              │
│                                        │
│ [✅ Confirm All]  [❌ Cancel]           │
│ [🔄 Re-analyze]  [📝 Add item]        │
└────────────────────────────────────────┘
```

**After confirmation:**

```
✅ Saved! Lunch logged.

Today so far: 1,340 / 2,195 kcal
Remaining: 855 kcal
Meals: 2/4 | Water: 1.5L | No runs yet

[📊 Full summary] [💧 +Water]
```

**Daily summary (/summary):**

```
📊 Monday, April 28, 2026

🍽 Meals:
  ☀️ Breakfast: 380 kcal (08:15)
  🌤 Lunch: 565 kcal (13:15)
  🌙 Dinner: 620 kcal (19:30)
  🍪 Snack: 180 kcal (16:00)

📥 Total in:  1,745 kcal
📤 Exercise:  -420 kcal (5.2km run)
📊 Net:       1,325 kcal
🎯 Target:    2,195 kcal
✅ Deficit:   -870 kcal

💪 Macros: P 128g (29%) | C 165g (38%) | F 65g (33%)
💧 Water: 2.1L
⚖️ Weight: 86.8 kg (trend: -0.3 this week)
```

### Security: Chat ID Whitelist

```python
ALLOWED_CHAT_IDS = [YOUR_CHAT_ID]  # From environment variable

async def security_check(update: Update) -> bool:
    if update.effective_chat.id not in ALLOWED_CHAT_IDS:
        await update.message.reply_text("⛔ Unauthorized.")
        return False
    return True
```

---

## 12. Dashboard (Analytics UI)

### Stage 1: Streamlit Dashboard

Minimal but functional. Connects directly to Supabase.

**Pages:**

1. **Daily View** — Calendar picker → meals with photos → item breakdown → macros pie chart
2. **Weekly Trend** — Line chart: daily calories in vs. target vs. TDEE, weight overlay
3. **Monthly Overview** — Heatmap of deficit/surplus days, average macros, weight trend
4. **AI Coach Reports** — Browse past weekly reports
5. **Food Diary** — Searchable list of all logged items, sorted by frequency
6. **Runs** — List + stats, weekly mileage, calorie burn trend

### Stage 3+: Next.js Dashboard (if needed)

Only if Streamlit becomes limiting. Adds:
- Mobile-responsive design
- Real-time updates
- Shareable reports (password-protected)

---

## 13. AI Prompts — Full Specifications

### 13.1 Vision Prompt (Food Identification)

```
SYSTEM:

You are a food identification specialist. Your task is to analyze a photo of
a meal and identify every distinct food item visible.

RULES:
1. Identify each food item separately (e.g., rice and chicken are two items)
2. Estimate weight in grams. Be CONSERVATIVE — round down when uncertain.
3. Match each item to the closest entry from the FOOD DATABASE below.
   Return the fdc_id from the database. If no close match exists, return
   fdc_id as null and provide your best description.
4. Include a confidence score (0.0 to 1.0) for your weight estimate.
   Be honest — if you cannot see the depth/thickness of the food, confidence
   should be below 0.5.
5. Return ONLY valid JSON. No explanations, no markdown.

FOOD DATABASE:
{usda_foundation_list}

USER'S COMMON CORRECTIONS (learn from these):
{few_shot_corrections}
Example: "When you see grilled chicken breast on a standard dinner plate,
estimate 130-150g, not 200g. User has corrected this 8 times."

OUTPUT FORMAT:
[
  {
    "ingredient_name": "grilled chicken breast",
    "ingredient_name_he": "חזה עוף צלוי",
    "fdc_id": 171077,
    "estimated_weight_grams": 150,
    "confidence": 0.65
  },
  {
    "ingredient_name": "white rice, cooked",
    "ingredient_name_he": "אורז לבן מבושל",
    "fdc_id": 168880,
    "estimated_weight_grams": 200,
    "confidence": 0.55
  }
]

USER MESSAGE:
[attached photo]
```

### 13.2 AI Coach Prompt (Weekly Analysis)

```
SYSTEM:

You are an experienced clinical dietitian analyzing a client's weekly food and
exercise log. Your goal is to help the client maintain a consistent calorie
deficit for healthy weight loss.

IMPORTANT: Perform ALL analysis, reasoning, calculations, and pattern
detection in English. Produce ONLY the final output summary in Hebrew.
Structure it clearly with headers and bullet points.

CLIENT PROFILE:
{user_profile_json}

THIS WEEK'S MEAL DATA (7 days):
{weekly_meals_json}

THIS WEEK'S EXERCISE DATA:
{weekly_runs_json}

WEIGHT MEASUREMENTS:
{weight_log_json}

LAST WEEK'S REPORT SUMMARY (for comparison):
{last_week_summary}

CALIBRATION STATUS:
{calibration_json}

ANALYZE THE FOLLOWING:

1. DEFICIT STATUS
   - Calculate average daily calorie intake vs. target
   - Calculate average daily net (intake - exercise burn)
   - Is the client on track for their weekly weight loss goal?

2. MACRO BALANCE
   - Average protein/carbs/fat split (grams and %)
   - Is protein sufficient for muscle preservation? (target: 1.6-2.0g per kg)
   - Fiber intake vs. 25g/day target

3. PATTERN DETECTION
   - Time-of-day patterns (late eating, long fasting gaps)
   - Post-exercise eating patterns (overcompensation after runs?)
   - Day-of-week patterns (weekend vs. weekday)
   - Recurring problematic foods (high calorie, low satiety)

4. WEEK-OVER-WEEK COMPARISON
   - What improved compared to last week?
   - What got worse?

5. ACTION ITEMS
   - Exactly 3 specific, actionable recommendations for next week
   - Ranked by expected impact on deficit

6. RECIPE SUGGESTIONS
   - 2 recipes that:
     a. Match the client's food preferences
     b. Are high protein, moderate calorie
     c. Are simple to prepare (< 30 min)
   - Include estimated calories and macros per serving

OUTPUT FORMAT (in Hebrew):
Use clear headers, bullet points, and numbers.
Include specific calorie numbers in every insight — don't be vague.
Be direct and honest — if the client overate, say so clearly.
```

### 13.3 Few-Shot Correction Builder

```python
def build_few_shot_corrections(limit: int = 10) -> str:
    """
    Queries ai_corrections table for most frequent/impactful corrections.
    Returns formatted text for inclusion in the Vision prompt.
    """
    corrections = query("""
        SELECT
            ingredient_name,
            meal_type,
            ROUND(AVG(ai_estimated_grams)) as avg_ai_estimate,
            ROUND(AVG(user_corrected_grams)) as avg_user_correction,
            COUNT(*) as times_corrected
        FROM ai_corrections
        GROUP BY ingredient_name, meal_type
        HAVING COUNT(*) >= 3
        ORDER BY COUNT(*) DESC
        LIMIT :limit
    """, limit=limit)

    lines = []
    for c in corrections:
        lines.append(
            f"- {c.ingredient_name} at {c.meal_type}: "
            f"you typically estimate {c.avg_ai_estimate}g but user corrects "
            f"to {c.avg_user_correction}g ({c.times_corrected} corrections). "
            f"Adjust your estimate accordingly."
        )

    return "\n".join(lines)
```

---

## 14. Privacy & Security

| Layer | Protection |
|---|---|
| **Telegram Bot** | Chat ID whitelist — only the registered user's chat_id is allowed; all other messages are rejected silently |
| **Supabase RLS** | Row Level Security enabled on all tables — queries filtered by authenticated user_id |
| **API Keys** | Stored in environment variables (`.env` file), never committed to code |
| **Photos** | Stored in Supabase Storage with private bucket — no public URLs |
| **OpenRouter** | Photos sent as base64, subject to OpenRouter's data retention policy; consider self-hosted models if this is a concern |
| **Self-hosted option** | Supabase can run locally via Docker for maximum privacy — no data leaves your machine except for AI API calls |
| **Encryption** | Supabase provides encryption at rest by default; enable SSL for all connections |

### Environment Variables Required

```bash
# .env file — NEVER commit this
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_ALLOWED_CHAT_ID=your_chat_id

OPENROUTER_API_KEY=your_openrouter_key
OPENROUTER_VISION_MODEL=openai/gpt-4o
OPENROUTER_COACH_MODEL=anthropic/claude-sonnet

SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_service_role_key

STRAVA_CLIENT_ID=your_strava_client_id
STRAVA_CLIENT_SECRET=your_strava_client_secret
STRAVA_REFRESH_TOKEN=your_strava_refresh_token

USDA_API_KEY=your_usda_api_key  # Only needed for initial data download
```

---

## 15. Development Roadmap

### Stage 1 — MVP: Core Meal Logging (Weeks 1–2)

The user can photograph meals, confirm items, and see daily calorie totals.

| Task | Priority | Est. Hours |
|---|---|---|
| Set up Supabase project + run schema SQL | P0 | 2 |
| Download + import USDA Foundation Foods into DB | P0 | 3 |
| Build Telegram bot skeleton (auth, commands, photo handler) | P0 | 4 |
| Implement Vision AI integration (OpenRouter + food list prompt) | P0 | 4 |
| Build inline keyboard for weight confirmation/correction | P0 | 4 |
| Implement nutrition calculation (fdc_id lookup × weight) | P0 | 2 |
| Save meals + meal_items to Supabase | P0 | 2 |
| Daily summary command (/summary) | P0 | 2 |
| Weight logging command (/weight) | P0 | 1 |
| Remaining calories command (/status) | P1 | 1 |
| Undo command (/undo) | P1 | 1 |
| **Stage 1 Total** | | **~26 hours** |

**Exit Criteria:** User can photograph a meal, see identified items with weights,
confirm or correct them, and view a daily calorie summary.

### Stage 2 — Learning + Exercise (Weeks 3–4)

The system starts learning from corrections and imports exercise data.

| Task | Priority | Est. Hours |
|---|---|---|
| Implement personal_foods + personal_food_logs tables + logic | P0 | 4 |
| Build weight suggestion engine (historical weights per meal type) | P0 | 3 |
| Implement auto-approve logic (confidence scoring) | P0 | 3 |
| Implement ai_corrections logging | P0 | 2 |
| Build few-shot correction builder for prompt improvement | P1 | 2 |
| Strava OAuth2 setup + activity import | P0 | 3 |
| MET-based calorie calculation for runs | P0 | 2 |
| Run logging command (/run) for manual entry | P1 | 1 |
| Water logging command (/water) | P1 | 1 |
| Update daily_summary with exercise data | P0 | 2 |
| **Stage 2 Total** | | **~23 hours** |

**Exit Criteria:** Frequently logged foods are auto-suggested or auto-approved.
Strava runs appear automatically in daily summary. Corrections improve future estimates.

### Stage 3 — AI Coach + Analytics (Weeks 5–6)

Weekly AI analysis and visual dashboard.

| Task | Priority | Est. Hours |
|---|---|---|
| BMR/TDEE calibration logic + calibration_log | P0 | 3 |
| Weekly calibration job (scheduled) | P0 | 2 |
| Calibration Telegram notifications | P1 | 1 |
| AI Coach weekly prompt + integration | P0 | 4 |
| Scheduled weekly report (Sunday 21:00) | P0 | 2 |
| Streamlit dashboard — daily view with meal photos | P0 | 4 |
| Streamlit dashboard — weekly calorie trend chart | P0 | 3 |
| Streamlit dashboard — weight trend chart | P1 | 2 |
| Streamlit dashboard — macro breakdown | P1 | 2 |
| Streamlit dashboard — AI Coach report viewer | P1 | 2 |
| **Stage 3 Total** | | **~25 hours** |

**Exit Criteria:** User receives weekly AI coaching reports. Dashboard shows trends,
drill-down to meals, and weight progression. BMR auto-adjusts with weight changes.

### Stage 4 — Enhancements (Weeks 7+)

| Task | Priority | Est. Hours |
|---|---|---|
| Barcode scanner (quagga2 or Telegram photo → Open Food Facts) | P2 | 4 |
| Garmin API integration (fallback for Strava) | P2 | 3 |
| Meal reminders ("Haven't logged since 12:00, did you eat?") | P2 | 2 |
| Food preference learning for AI Coach recipes | P2 | 2 |
| Next.js dashboard (if Streamlit is limiting) | P3 | 15 |
| Monthly PDF report generation | P3 | 4 |
| Photo comparison (same meal over time) | P3 | 3 |
| **Stage 4 Total** | | **~33 hours** |

---

## 16. Cost Estimate

### Monthly Costs (Single User)

| Component | Calculation | Monthly Cost |
|---|---|---|
| **Supabase** | Free tier (500MB DB, 1GB storage) | $0 |
| **OpenRouter — Vision** | ~90 meals/month × ~$0.05/call (GPT-4o with image) | ~$4.50 |
| **OpenRouter — AI Coach** | 4 weekly reports × ~$0.30/call (Claude Sonnet, long prompt) | ~$1.20 |
| **USDA API** | Free (data downloaded locally) | $0 |
| **Strava API** | Free tier | $0 |
| **Telegram Bot** | Free | $0 |
| **Hosting (bot)** | Railway free tier / local machine | $0 |
| **Streamlit** | Local or Streamlit Community Cloud (free) | $0 |
| **Total** | | **~$5.70/month** |

### Cost Optimization

- Use **GPT-4o-mini** or **Claude Haiku** for vision (cheaper, still good for food ID):
  drops to ~$1.50/month for vision calls
- Cache nutrition lookups (local DB already does this)
- Batch corrections into weekly prompt updates (not per-correction)

### Projected Total: **$3–6/month**

---

## Appendix A: File Structure

```
caltrack/
├── bot/
│   ├── __init__.py
│   ├── main.py                 # Bot entry point, handlers registration
│   ├── handlers/
│   │   ├── photo.py            # Meal photo processing flow
│   │   ├── commands.py         # /weight, /water, /run, /summary, etc.
│   │   ├── callbacks.py        # Inline keyboard callback handlers
│   │   └── admin.py            # /calibrate, /stats, /export
│   ├── services/
│   │   ├── vision.py           # OpenRouter Vision API integration
│   │   ├── nutrition.py        # USDA lookup + nutrition calculation
│   │   ├── personal_foods.py   # Learning engine + auto-approve logic
│   │   ├── calibration.py      # BMR/TDEE calculation + recalibration
│   │   ├── strava.py           # Strava API sync
│   │   ├── coach.py            # AI Coach weekly analysis
│   │   └── daily_summary.py    # Summary computation + formatting
│   ├── db/
│   │   ├── supabase_client.py  # Supabase connection + helpers
│   │   ├── models.py           # Pydantic models for all tables
│   │   └── queries.py          # Reusable SQL queries
│   └── utils/
│       ├── config.py           # Environment variables + settings
│       ├── formatters.py       # Telegram message formatting
│       └── met_calculator.py   # MET-based calorie burn formulas
├── dashboard/
│   ├── app.py                  # Streamlit dashboard
│   ├── pages/
│   │   ├── daily.py
│   │   ├── weekly.py
│   │   ├── monthly.py
│   │   ├── food_diary.py
│   │   ├── runs.py
│   │   └── coach_reports.py
│   └── components/
│       ├── charts.py
│       └── filters.py
├── data/
│   └── usda_foundation.csv     # Downloaded USDA Foundation Foods
├── scripts/
│   ├── import_usda.py          # One-time: load USDA data into Supabase
│   ├── setup_supabase.sql      # Full schema creation script
│   └── seed_profile.py         # Initial user profile setup
├── .env                        # API keys (NEVER commit)
├── .env.example                # Template for .env
├── requirements.txt
├── Dockerfile                  # For deployment
└── README.md
```

---

## Appendix B: Key Decisions Log

| Decision | Choice | Rationale | Alternative Considered |
|---|---|---|---|
| Primary UI | Telegram Bot | Minimal friction, camera access, already installed, private | PWA (more friction for photo upload) |
| Database | Supabase | Managed Postgres + Storage + RLS, free tier sufficient | SQLite (no cloud sync, no photo storage) |
| Nutrition source | USDA Foundation Foods (local) | No API latency, no search ambiguity, exact fdc_id matching | USDA API search (unreliable results) |
| Weight estimation | AI estimate + mandatory user confirmation | AI alone is ~70% accurate, unacceptable for calorie deficit tracking | Reference object in photo (impractical) |
| Learning approach | Historical weight logs per food per meal_type | Context-aware, reflects actual usage patterns | Simple averages (loses meal-type context) |
| AI analysis language | English thinking, Hebrew output | Models reason better in English, saves tokens | Full Hebrew (worse analysis quality) |
| Exercise data | Strava import in Stage 2 | Code already exists, critical for TDEE accuracy | Manual only until Stage 4 (loses data quality) |
| Target calibration | Auto-recalculate weekly based on weight trend | Prevents plateau from fixed targets on changing body weight | Manual adjustment (user will forget) |
