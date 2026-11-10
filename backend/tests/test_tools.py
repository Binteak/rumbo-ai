import pytest

from app.agent.tools import ToolContext, ToolError, execute_tool, tool_schemas


def test_schemas_are_generated_from_pydantic():
    names = {s["name"] for s in tool_schemas()}
    assert names == {
        "search_destinations",
        "get_climate",
        "estimate_budget",
        "build_itinerary",
        "search_travel_guides",
        "save_trip",
    }
    climate = next(s for s in tool_schemas() if s["name"] == "get_climate")
    assert climate["input_schema"]["required"] == ["destination_id", "month"]


def test_search_ranks_by_interests_and_respects_budget():
    out = execute_tool("search_destinations", {"interests": ["playa"], "max_daily_budget_eur": 60, "style": "mochilero"})
    assert out["results"]
    assert all(r["daily_cost_eur"] <= 60 for r in out["results"])
    assert "playa" in out["results"][0]["why"]


def test_search_without_results_raises():
    with pytest.raises(ToolError, match="presupuesto"):
        execute_tool("search_destinations", {"max_daily_budget_eur": 1})


def test_climate_verdict():
    out = execute_tool("get_climate", {"destination_id": "reikiavik", "month": 1})
    assert out["avg_temp_c"] == 0
    assert "frío" in out["verdict"]


def test_budget_totals_add_up():
    out = execute_tool("estimate_budget", {"destination_id": "lisboa", "days": 3, "travelers": 2, "style": "confort"})
    assert out["total_per_person_eur"] == sum(out["per_person"].values())
    assert out["total_eur"] == out["total_per_person_eur"] * 2


def test_itinerary_has_one_entry_per_day_and_night_plans_at_night():
    out = execute_tool("build_itinerary", {"destination_id": "lisboa", "days": 3, "interests": ["nocturna"]})
    assert [d["day"] for d in out["days"]] == [1, 2, 3]
    for day in out["days"]:
        for act in day["activities"]:
            if act["category"] == "nocturna":
                assert act["slot"] == "noche"


def test_unknown_destination_lists_valid_ids():
    with pytest.raises(ToolError, match="Ids válidos"):
        execute_tool("get_climate", {"destination_id": "atlantida", "month": 5})


def test_invalid_args_are_reported_for_self_correction():
    with pytest.raises(ToolError, match="month"):
        execute_tool("get_climate", {"destination_id": "kioto", "month": 13})


def test_save_trip_recomputes_plan_on_server():
    saved = []
    ctx = ToolContext(save_trip=lambda d: saved.append(d) or {**d, "id": 7})
    out = execute_tool(
        "save_trip", {"title": "Escapada", "destination_id": "seul", "days": 2, "summary": "Prueba", "month": 10}, ctx
    )
    assert out == {"trip_id": 7, "status": "guardado"}
    assert len(saved[0]["itinerary"]) == 2
    assert saved[0]["climate"]["month"] == "octubre"
