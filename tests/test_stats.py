import numpy as np
import pytest

from qaudit.stats import (matrix,probabilities,metrics,fit_temperature,bootstrap_transfer,conclusion)


def test_hand_calculated_scores():
    p=np.array([[.75,.25],[.1,.9]])
    m=metrics(np.log(p),np.array([0,0]),bins=10)
    assert m["accuracy"]==.5
    assert m["brier"]==pytest.approx((.125+1.62)/2)
    assert m["nll"]==pytest.approx((-np.log(.75)-np.log(.1))/2)
    assert m["ece"]==pytest.approx((.25+.9)/2)


def test_variable_choice_padding_and_extreme_logits():
    x=matrix([[10000,9999],[-10000,-10001,-10002]])
    p=probabilities(x)
    assert p[0,2]==0
    assert np.isfinite(p).all()
    np.testing.assert_allclose(p.sum(axis=1),1)
    for t in [.05,1,20]:
        np.testing.assert_array_equal(probabilities(x,t).argmax(axis=1),x.argmax(axis=1))


def test_temperature_fits_overconfidence_without_changing_answers():
    x=np.tile([4.,0.],(100,1));y=np.array([0]*75+[1]*25)
    fit=fit_temperature(x,y)
    assert fit["temperature"]==pytest.approx(4/np.log(3),rel=1e-5)
    assert metrics(x,y,fit["temperature"])["nll"]<metrics(x,y)["nll"]
    assert metrics(x,y,fit["temperature"])["accuracy"]==.75


def test_bootstrap_identical_reference_and_quantized_is_exactly_zero():
    x=matrix([[2,1],[1,2],[3,1],[1,3]]);y=np.array([0,1,1,0])
    result=bootstrap_transfer(x,x,y,x,y,reps=20,seed=17)
    assert result["estimate"]==0
    assert result["ci95"]==[0,0]


def test_empty_selective_predictions_are_explicit():
    m=metrics(np.zeros((4,3)),np.array([0,1,2,0]))
    assert m["selective"][-1]["answered"]==0
    assert m["selective"][-1]["error_rate"] is None


@pytest.mark.parametrize("t",[0,-1,np.nan,np.inf])
def test_invalid_temperatures_rejected(t):
    with pytest.raises(ValueError):
        probabilities(np.ones((1,2)),t)


def test_claim_language_is_bounded():
    assert "inconclusive" in conclusion({"estimate":.01,"ci95":[-.01,.03]})
    assert "little practical" in conclusion({"estimate":0,"ci95":[-.002,.002]})
    assert "worsens" in conclusion({"estimate":-.02,"ci95":[-.03,-.015]})
