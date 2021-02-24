"""
Activity level classification based on accelerometer data

Lukas Adamowicz
Pfizer DMTI 2021
"""
from skimu.base import _BaseProcess

from skimu.activity.metrics import *

# ==========================================================
# Activity cutpoints
_base_cutpoints = {}

_base_cutpoints["esliger_lwrist_adult"] = {
    "metric": metric_enmo,
    "kwargs": {"take_abs": True},
    "sedentary": 217 / 80 / 60,  # paper at 80hz, summed for each minute long window
    "light": 644 / 80 / 60,
    "moderate": 1810 / 80 / 60
}

_base_cutpoints["esliger_rwirst_adult"] = {
    "metric": metric_enmo,
    "kwargs": {"take_abs": True},
    "sedentary": 386 / 80 / 60,  # paper at 80hz, summed for each 1min window
    "light": 439 / 80 / 60,
    "moderate": 2098 / 80 / 60
}

_base_cutpoints["esliger_lumbar_adult"] = {
    "metric": metric_enmo,
    "kwargs": {"take_abs": True},
    "sedentary": 77 / 80 / 60,  # paper at 80hz, summed for each 1min window
    "light": 219 / 80 / 60,
    "moderate": 2056 / 80 / 60
}

_base_cutpoints["schaefer_ndomwrist_child6-11"] = {
    "metric": metric_bfen,
    "kwargs": {"low_cutoff": 0.2, "high_cutoff": 15, "trim_zero": False},
    "sedentary": 0.190,
    "light": 0.314,
    "moderate": 0.998
}

_base_cutpoints["phillips_rwrist_child8-14"] = {
    "metric": metric_enmo,
    "kwargs": {"take_abs": True},
    "sedentary": 6 / 80,  # paper at 80hz, summed for each 1s window
    "light": 21 / 80,
    "moderate": 56 / 80
}

_base_cutpoints["phillips_lwrist_child8-14"] = {
    "metric": metric_enmo,
    "kwargs": {"take_abs": True},
    "sedentary": 7 / 80,
    "light": 19 / 80,
    "moderate": 60 / 80
}

_base_cutpoints["phillips_hip_child8-14"] = {
    "metric": metric_enmo,
    "kwargs": {"take_abs": True},
    "sedentary": 3 / 80,
    "light": 16 / 80,
    "moderate": 51 / 80
}

_base_cutpoints["vaha-ypya_hip_adult"] = {
    "metric": metric_mad,
    "kwargs": {},
    "light": 0.091,  # originally presented in mg
    "moderate": 0.414
}

_base_cutpoints["hildebrand_hip_adult_actigraph"] = {
    "metric": metric_enmo,
    "kwargs": {"take_abs": False, "trim_zero": True},
    "sedentary": 0.0474,
    "light": 0.0691,
    "moderate": 0.2587
}

_base_cutpoints["hildebrand_hip_adult_geneactv"] = {
    "metric": metric_enmo,
    "kwargs": {"take_abs": False, "trim_zero": True},
    "sedentary": 0.0469,
    "light": 0.0687,
    "moderate": 0.2668
}

_base_cutpoints["hildebrand_wrist_adult_actigraph"] = {
    "metric": metric_enmo,
    "kwargs": {"take_abs": False, "trim_zero": True},
    "sedentary": 0.0448,
    "light": 0.1006,
    "moderate": 0.4288
}

_base_cutpoints["hildebrand_wrist_adult_geneactiv"] = {
    "metric": metric_enmo,
    "kwargs": {"take_abs": False, "trim_zero": True},
    "sedentary": 0.0458,
    "light": 0.0932,
    "moderate": 0.4183
}

_base_cutpoints["hildebrand_hip_child7-11_actigraph"] = {
    "metric": metric_enmo,
    "kwargs": {"take_abs": False, "trim_zero": True},
    "sedentary": 0.0633,
    "light": 0.1426,
    "moderate": 0.4646
}

_base_cutpoints["hildebrand_hip_child7-11_geneactiv"] = {
    "metric": metric_enmo,
    "kwargs": {"take_abs": False, "trim_zero": True},
    "sedentary": 0.0641,
    "light": 0.1528,
    "moderate": 0.5143
}

_base_cutpoints["hildebrand_wrist_child7-11_actigraph"] = {
    "metric": metric_enmo,
    "kwargs": {"take_abs": False, "trim_zero": True},
    "sedentary": 0.0356,
    "light": 0.2014,
    "moderate": 0.707
}

_base_cutpoints["hildebrand_wrist_child7-11_geneactiv"] = {
    "metric": metric_enmo,
    "kwargs": {"take_abs": False, "trim_zero": True},
    "sedentary": 0.0563,
    "light": 0.1916,
    "moderate": 0.6958
}

_base_cutpoints["migueles_wrist_adult"] = {
    "metric": metric_enmo,
    "kwargs": {"take_abs": False, "trim_zero": True},
    "sedentary": 0.050,
    "light": 0.110,
    "moderate": 0.440
}


def get_available_cutpoints():
    """
    Print the available cutpoints for activity level segmentation.
    """
    print(_base_cutpoints.keys())


class MVPActivityClassification(_BaseProcess):
    """
    Classify accelerometer data into different activity levels as a proxy for assessing physical
    activity energy expenditure (PAEE). Levels are sedentary, light, moderate, and vigorous.

    Parameters
    ----------
    cutpoints : {str, dict, list}, optional
        Cutpoints to use for sedentary/light/moderate/vigorous activity classification. Default
        is "migueles_wrist_adult". For a list of all available metrics use
        `skimu.activity.get_available_cutpoints()`. Custom cutpoints can be provided in a
        dictionary (see :ref:`Using Custom Cutpoints`).
    """
    def __init__(self, cutpoints="migueles_wrist_adult"):
        cutpoints = _base_cutpoints.get(cutpoints, _base_cutpoints["migueles_wrist_adult"])

        super().__init__(
            cutpoints=cutpoints
        )

    def predict(self, time=None, accel=None, *, wear=None, **kwargs):
        """
        predict(time, accel, *, wear=None)

        Compute the time spent in different activity levels.

        Parameters
        ----------
        time
        accel
        wear
        kwargs

        Returns
        -------

        """
