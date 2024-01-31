import os
import warnings

import numpy as np

from .. import utils
from ..coords import Coordinates, dx_dy_to_phi_theta
from ..instrument import Instrument, get_instrument
from ..pointing import Pointing, get_pointing
from ..site import Site, get_site
from ..tod import TOD

here, this_filename = os.path.split(__file__)


class InvalidSimulationParameterError(Exception):
    def __init__(self, invalid_keys):
        super().__init__(
            f"The parameters {invalid_keys} are not valid simulation parameters!"
        )


master_params = utils.io.read_yaml(f"{here}/default_params.yml")


def parse_sim_kwargs(kwargs, master_kwargs, strict=False):
    parsed_kwargs = {k: {} for k in master_kwargs.keys()}
    invalid_kwargs = {}

    for k, v in kwargs.items():
        parsed = False
        for sub_type, sub_kwargs in master_kwargs.items():
            if k in sub_kwargs.keys():
                parsed_kwargs[sub_type][k] = v
                parsed = True
        if not parsed:
            invalid_kwargs[k] = v

    if len(invalid_kwargs) > 0:
        if strict:
            raise InvalidSimulationParameterError(
                invalid_keys=list(invalid_kwargs.keys())
            )

    return parsed_kwargs


class BaseSimulation:
    """
    The base class for a simulation. This is an ingredient in every simulation.
    """

    def __init__(
        self,
        instrument: Instrument or str = "default",
        pointing: Pointing or str = "stare",
        site: Site or str = "default",
        verbose=False,
        **kwargs,
    ):
        if hasattr(self, "boresight"):
            return

        self.verbose = verbose

        self.data = {}

        parsed_sim_kwargs = parse_sim_kwargs(kwargs, master_params)

        if type(instrument) is Instrument:
            self.instrument = instrument
        else:
            self.instrument = get_instrument(
                instrument_name=instrument, **parsed_sim_kwargs["instrument"]
            )

        if type(pointing) is Pointing:
            self.pointing = pointing
        else:
            self.pointing = get_pointing(
                scan_pattern=pointing, **parsed_sim_kwargs["pointing"]
            )

        if type(site) is Site:
            self.site = site
        else:
            self.site = get_site(site_name=site, **parsed_sim_kwargs["site"])

        self.boresight = Coordinates(
            self.pointing.time,
            self.pointing.phi,
            self.pointing.theta,
            location=self.site.earth_location,
            frame=self.pointing.pointing_frame,
        )

        if self.pointing.max_vel > np.radians(self.instrument.vel_limit):
            raise warnings.warn(
                (
                    f"The maximum velocity of the boresight ({np.degrees(self.pointing.max_vel):.01f} deg/s) exceeds "
                    f"the maximum velocity of the instrument ({self.instrument.vel_limit:.01f} deg/s)."
                ),
            )

        if self.pointing.max_acc > np.radians(self.instrument.acc_limit):
            raise warnings.warn(
                (
                    f"The maximum acceleration of the boresight ({np.degrees(self.pointing.max_acc):.01f} deg/s^2) exceeds "
                    f"the maximum acceleration of the instrument ({self.instrument.acc_limit:.01f} deg/s^2)."
                ),
            )

        det_az, det_el = dx_dy_to_phi_theta(
            *self.instrument.offsets.T[..., None], self.boresight.az, self.boresight.el
        )

        self.det_coords = Coordinates(
            self.boresight.time,
            det_az,
            det_el,
            location=self.site.earth_location,
            frame="az_el",
        )

    def _run(self):
        raise NotImplementedError()

    def run(self):
        self._run()

        abscal = 1.0
        if hasattr(self, "atmospheric_transmission"):
            abscal /= self.atmospheric_transmission.mean()

        tod = TOD(
            data=self.data,
            dets=self.instrument.dets.df,
            # boresight=self.boresight,
            coords=self.det_coords,
            abscal=abscal,
        )

        return tod
