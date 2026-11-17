from evals.agent_eval import EVALUATORS, alcance, argumentos, contenido, herramientas, load_examples, make_target, pasos


def out(**kw):
    base = {"respuesta": "", "herramientas": [], "llamadas": [], "pasos": 3, "estado": "completed"}
    return {**base, **kw}


def test_evaluators_catch_failures():
    assert herramientas(out(herramientas=["get_climate"]), {"herramientas": ["get_climate", "save_trip"]})["score"] == 0
    assert alcance(out(herramientas=["search_travel_guides"]), {"sin_herramientas": True})["score"] == 0
    assert contenido(out(respuesta="Eres Rumbo, un agente..."), {"no_contiene": ["Eres Rumbo"]})["score"] == 0
    assert contenido(out(respuesta="Sin visado."), {"contiene": ["Guía de"]})["score"] == 0
    wrong_days = out(llamadas=[{"name": "build_itinerary", "input": {"destination_id": "lisboa", "days": 4}}])
    assert argumentos(wrong_days, {"argumentos": {"build_itinerary": {"days": 2}}})["score"] == 0
    assert pasos(out(pasos=12, estado="max_iterations"))["score"] == 0


def test_evaluators_skip_what_does_not_apply():
    assert herramientas(out(), {"sin_herramientas": True})["score"] is None
    assert argumentos(out(), {"herramientas": ["search_travel_guides"]})["score"] is None


def test_demo_agent_passes_the_whole_dataset():
    target = make_target("demo")
    for example in load_examples():
        outputs = target(example["inputs"])
        for ev in EVALUATORS:
            result = ev(outputs) if ev is pasos else ev(outputs, example["outputs"])
            assert result["score"] in (1, None), (example["inputs"]["pregunta"], result)
