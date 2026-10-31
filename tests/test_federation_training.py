"""Independent scalar-gradient reference for the fixed no-rescaling trainer."""
import struct
from uuid import UUID

import pytest

from suan.federation.protocol import model_layout
from suan.federation.training import fit, TrainingCancelled
from suan.federation.updates import encode_arrays


def spec(dtype="f64", strategy="fedavg", steps=5):
    return {"format": "stk.federation-training-spec/1", "trainer": "linear-regression/1",
            "features": [{"name": "x0", "unit": "1"}], "targets": [{"name": "y0", "unit": "1"}],
            "dtype": dtype, "normalization": "none", "steps": steps, "learning_rate": .15,
            "strategy": strategy, "proximal_mu": .7 if strategy == "fedprox" else 0}


def model(settings=None, weights=.25, bias=-.2):
    settings = settings or spec()
    code = "f" if settings["dtype"] == "f32" else "d"
    return encode_arrays([{**desc, "data": struct.pack("<" + code, value)}
                          for desc, value in zip(model_layout(settings), (weights, bias))], kind="model")


@pytest.mark.parametrize("dtype", ["f32", "f64"])
@pytest.mark.parametrize("strategy", ["fedavg", "fedprox"])
def test_fixed_trainer_matches_independent_per_example_gradient(dtype, strategy):
    settings = spec(dtype, strategy)
    xs = [-2., -.5, 0., 1., 3.]
    ys = [2 * x - 1 for x in xs]
    code = "f" if dtype == "f32" else "d"
    def rounded(value):
        return struct.unpack("<" + code, struct.pack("<" + code, value))[0]
    w0, b0 = rounded(.25), rounded(-.2)
    w, b = w0, b0
    for _ in range(settings["steps"]):
        errors = [w * x + b - y for x, y in zip(xs, ys)]
        dw = 2 * sum(e * x for e, x in zip(errors, xs)) / len(xs) + settings["proximal_mu"] * (w-w0)
        db = 2 * sum(errors) / len(xs) + settings["proximal_mu"] * (b-b0)
        w, b = rounded(w - .15 * dw), rounded(b - .15 * db)
    actual_w, actual_b, loss = fit(settings, [[w0]], [b0], [[x] for x in xs], [[y] for y in ys])
    assert actual_w.item() == pytest.approx(w, rel=1e-6 if dtype == "f32" else 1e-14)
    assert actual_b.item() == pytest.approx(b, rel=1e-6 if dtype == "f32" else 1e-14)
    assert loss == pytest.approx(sum((w*x+b-y)**2 for x,y in zip(xs,ys))/len(xs), rel=1e-6)


def test_multi_target_gradient_averages_over_all_observations():
    settings = spec(steps=1)
    settings["targets"].append({"name": "second", "unit": "1"})
    w, b, _ = fit(settings, [[0., 0.]], [0., 0.], [[1.], [2.]], [[2., 4.], [4., 8.]])
    assert w.tolist()[0] == pytest.approx([.75, 1.5])
    assert b.tolist() == pytest.approx([.45, .9])


def test_cancellation_and_nonfinite_overflow_are_not_results():
    with pytest.raises(TrainingCancelled):
        fit(spec(), [[0.]], [0.], [[1.]], [[1.]], cancel=lambda: True)
    with pytest.raises((ValueError, FloatingPointError)):
        fit(spec(), [[1.]], [0.], [[1e308]], [[-1e308]])
