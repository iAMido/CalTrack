"""
Shared Israeli portion-size + nutrition reference values.

Used by:
- bot/services/vision.py        (meal photo prompt)
- bot/handlers/commands.py      (/add freeform AI breakdown prompt)
- running-coach analyze route   (kept in sync manually)

Update both copies if you change this list.
"""

# Typical Israeli serving sizes in grams.
# Used by AI prompts as anchors when the user does not specify a weight.
PORTION_ANCHORS_G = {
    "pita": 60,
    "tahini_serving": 30,
    "hummus_serving": 80,
    "schnitzel_portion": 150,
    "egg": 50,
    "tbsp_default": 15,
    "tbsp_cottage": 12,
    "burekas_piece": 90,
    "shawarma_portion": 200,
    "rice_cooked_side": 150,
    "salad_side": 120,
}

# Calorie-per-100g reference values for common foods.
# AI must never return 0 for real foods; these anchor the lower bound.
CALORIE_REFERENCE_PER_100G = {
    "egg": 155,
    "cottage_cheese": 98,
    "feta_bulgarian": 264,
    "oats": 389,
    "rice_cooked": 130,
    "chicken_breast": 165,
    "bread": 265,
    "olive_oil": 884,
    "butter": 717,
    "hummus": 166,
    "tahini": 595,
    "avocado": 160,
    "burekas": 360,
    "shawarma_meat": 290,
    "falafel_ball": 333,
    "schnitzel": 280,
}


def portion_anchor_prompt_block() -> str:
    """Return a prompt-ready block of portion + calorie anchors."""
    return (
        "ISRAELI PORTION ANCHORS (use when weight is unknown):\n"
        "- pita ~60g, tahini serving ~30g, hummus serving ~80g, "
        "schnitzel portion ~150g, single burekas ~90g, shawarma portion ~200g\n"
        "- 1 egg = ~50g (1 omelette from 2 eggs = ~100g of egg)\n"
        "- 1 tablespoon (tbsp/tbs) = ~15g for most foods, ~12g for cottage cheese\n"
        "\n"
        "CALORIE REFERENCE per 100g (never return 0 for real food):\n"
        "- egg=155, cottage cheese=98, Bulgarian/feta cheese=264, oats=389\n"
        "- rice cooked=130, chicken breast=165, bread=265\n"
        "- olive oil=884, butter=717, hummus=166, tahini=595\n"
        "- avocado=160, burekas=360, shawarma meat=290, falafel ball=333, schnitzel=280\n"
    )


def vision_portion_block() -> str:
    """Extra plate-perspective guidance for the meal-photo prompt."""
    return (
        "PLATE PERSPECTIVE GUIDANCE:\n"
        "- Standard dinner plate ~26-28cm diameter, salad plate ~20cm.\n"
        "- Top-down photos hide depth/thickness — if you cannot see depth, "
        "estimate the THINNER side and lower confidence to <0.5.\n"
        "- A pita covering half the plate is ~60-80g, not 200g.\n"
        "- Cooked rice fills ~3/4 of a small bowl at ~150g, not 300g.\n"
    )
