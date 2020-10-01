"""
Gait detection, processing, and analysis from wearable inertial sensor data

Lukas Adamowicz
Pfizer DMTI 2020
"""
from warnings import warn

from numpy import mean, std, sum, diff, sqrt, cov, abs, where, argmax, insert, append, sign, \
    round, unique, array, full, fft, nan, float_
from scipy.signal import detrend, butter, sosfiltfilt, find_peaks
from scipy.integrate import cumtrapz
from pywt import cwt

from PfyMU.base import _BaseProcess
from PfyMU.gait.bout_detection import get_lgb_gait_classification


class Gait(_BaseProcess):
    # gait parameters
    params = [
        'stride time',
        'stance time',
        'swing time',
        'step time',
        'initial double support',
        'terminal double support',
        'double support',
        'single support',
        'step length',
        'stride length',
        'gait speed',
        'cadence',
        'step regularity - V',  # complex asymmetry param
        'stride regularity - V'  # complex asymmetry param
    ]

    # basic asymmetry parameters
    asym_params = [
        'stride time', 'stance time', 'swing time', 'step time', 'initial double support',
        'terminal double support', 'double support', 'single support', 'step length',
        'stride length'
    ]

    def __init__(self, use_cwt_scale_relation=True, min_bout_time=5.0,
                 max_bout_separation_time=0.5, max_stride_time=2.25, loading_factor=0.2,
                 height_factor=0.53, leg_length=False, filter_order=4, filter_cutoff=20.0):
        """
        Detect gait, extract gait events (heel-strikes, toe-offs), and compute gait metrics from
        inertial data collected from a lumbar mounted wearable inertial measurement unit

        Parameters
        ----------
        use_cwt_scale_relation : bool, optional
            Use the optimal scale/frequency relationship defined in [5]_. This changes which
            scale is used for the smoothing/differentiation operation performed with the
            continuous wavelet transform. Default is True. See Notes for a caveat of the
            relationship
        min_bout_time : float, optional
            Minimum time in seconds for a gait bout. Default is 5s
        max_bout_separation_time : float, optional
            Maximum time in seconds between two bouts of gait for them to be merged into 1 gait
            bout. Default is 0.5s
        max_stride_time : float, optional
            The maximum time in seconds for a stride, for optimization of gait events detection.
            Default is 2.25s
        loading_factor : float, optional
            The factor to determine maximum loading time (initial double support time), for
            optimization of gait events detection. Default is 0.2
        height_factor : float, optional
            The factor multiplied by height to obtain an estimate of leg length.
            Default is 0.53 [4]_. Ignored if `leg_length` is `True`
        leg_length : bool, optional
            If the actual leg length will be provided. Setting to true would have the same effect
            as setting height_factor to 1.0 while providing leg length. Default is False
        filter_order : int, optional
            Acceleration low-pass filter order. Default is 4
        filter_cutoff : float, optional
            Acceleration low-pass filter cutoff in Hz. Default is 20.0Hz

        Notes
        -----
        The optimal scale/frequency relationship found in [5]_ was based on a cohort of only young
        women students. While it is recommended to use this relationship, the user should be aware
        of this shortfall in the generation of the relationship.

        3 optimizations are performed on the detected events to minimize false positives.

        1. Loading time (initial double support) must be less than
        :math:`loading_factor * max_stride_time`
        2. Stance time must be less than
        :math:`(max_stride_time/2) + loading_factor * max_stride_time`
        3. Stride time must be less than `max_stride_time`

        References
        ----------
        .. [1] B. Najafi, K. Aminian, A. Paraschiv-Ionescu, F. Loew, C. J. Bula, and P. Robert,
            “Ambulatory system for human motion analysis using a kinematic sensor: monitoring of
            daily physical activity in the elderly,” IEEE Transactions on Biomedical Engineering,
            vol. 50, no. 6, pp. 711–723, Jun. 2003, doi: 10.1109/TBME.2003.812189.
        .. [2] W. Zijlstra and A. L. Hof, “Assessment of spatio-temporal gait parameters from
            trunk accelerations during human walking,” Gait & Posture, vol. 18, no. 2, pp. 1–10,
            Oct. 2003, doi: 10.1016/S0966-6362(02)00190-X.
        .. [3] J. McCamley, M. Donati, E. Grimpampi, and C. Mazzà, “An enhanced estimate of initial
            contact and final contact instants of time using lower trunk inertial sensor data,”
            Gait & Posture, vol. 36, no. 2, pp. 316–318, Jun. 2012,
            doi: 10.1016/j.gaitpost.2012.02.019.
        .. [4] S. Del Din, A. Godfrey, and L. Rochester, “Validation of an Accelerometer to
            Quantify a Comprehensive Battery of Gait Characteristics in Healthy Older Adults and
            Parkinson’s Disease: Toward Clinical and at Home Use,” IEEE J. Biomed. Health Inform.,
            vol. 20, no. 3, pp. 838–847, May 2016, doi: 10.1109/JBHI.2015.2419317.
        .. [5] C. Caramia, C. De Marchis, and M. Schmid, “Optimizing the Scale of a Wavelet-Based
            Method for the Detection of Gait Events from a Waist-Mounted Accelerometer under
            Different Walking Speeds,” Sensors, vol. 19, no. 8, p. 1869, Jan. 2019,
            doi: 10.3390/s19081869.
        .. [6] C. Buckley et al., “Gait Asymmetry Post-Stroke: Determining Valid and Reliable
            Methods Using a Single Accelerometer Located on the Trunk,” Sensors, vol. 20, no. 1,
            Art. no. 1, Jan. 2020, doi: 10.3390/s20010037.
        """
        super().__init__('Gait Process')

        self.use_opt_scale = use_cwt_scale_relation
        self.min_bout = min_bout_time
        self.max_bout_sep = max_bout_separation_time

        self.max_stride_time = max_stride_time
        self.loading_factor = loading_factor

        self.height_factor = height_factor
        self.leg_length = leg_length

        self.filt_ord = filter_order
        self.filt_cut = filter_cutoff

    def _predict(self, *, time=None, accel=None, gyro=None, height=None, **kwargs):
        """
        Get the gait events and metrics from a time series signal

        Parameters
        ----------
        time : numpy.ndarray
            (N, ) array of unix timestamps, in seconds
        accel : numpy.ndarray
            (N, 3) array of accelerations measured by centrally mounted lumbar device, in
            units of 'g'
        gyro : numpy.ndarray, optional
            (N, 3) array of angular velocities measured by the same centrally mounted lumbar
            device, in units of 'deg/s'. Only optionally used if provided. Main functionality
            is to allow distinguishing step sides.
        height : float, optional
            Either height (False) or leg length (True) of the subject who wore the inertial
            measurement device, in meters, depending on `leg_length`. If not provided,
            spatial metrics will not be computed

        Returns
        -------
        gait_results : dict
        """
        super()._predict(time=time, accel=accel, gyro=gyro, **kwargs)

        if 'height' is None:
            warn('height not provided, not computing spatial metrics', UserWarning)
        else:
            # if not providing leg length (default), multiply height by the height factor
            if not self.leg_length:
                leg_length = self.height_factor * height
            else:
                leg_length = height

        # compute fs/delta t
        dt = mean(diff(time[:500]))

        # check if windows exist for days
        if self._days in kwargs:
            days = kwargs[self._days]
        else:
            days = [(0, accel.shape[0])]

        # get the gait classifications
        gait_class = get_lgb_gait_classification(accel, 1 / dt)

        # figure out vertical axis
        acc_mean = mean(accel, axis=0)
        v_axis = argmax(abs(acc_mean))

        # original scale. compute outside loop.
        # 1.25 comes from original paper, corresponds to desired frequency
        # 0.4 comes from using the 'gaus1' wavelet
        scale_original = round(0.4 / (2 * 1.25 * 1/dt)) - 1

        gait = {
            'Day N': [],
            'Bout N': [], 'Bout Start': [], 'Bout Duration': [], 'Bout Steps': [],
            'IC': [], 'FC': [], 'FC opp foot': [],
            'b valid cycle': [], 'delta h': []
        }
        # allocate params just for order of creation
        for p in self.params:
            gait[f'PARAM:{p}'] = None
        for p in self.asym_params:
            gait[f'PARAM:{p} asymmetry'] = None
        # allocate regularity params
        gait['PARAM:step regularity - V'] = []
        gait['PARAM:stride regularity - V'] = []

        ig = 0  # keep track of where everything is in the cycle

        for iday, day_idx in enumerate(days):
            start, stop = day_idx

            # GET GAIT BOUTS
            # ======================================
            gait_bouts = self._get_gait_bouts(gait_class[start:stop])

            for ibout, bout in enumerate(gait_bouts):
                bstart = start + bout[0]
                # GET GAIT EVENTS
                # ======================================
                vert_acc = detrend(accel[bstart:start+bout[1], v_axis])

                # low-pass filter
                sos = butter(self.filt_ord, 2 * self.filt_cut * dt, btype='low', output='sos')
                fvert_acc = sosfiltfilt(sos, vert_acc)

                # first integrate the vertical acceleration to get vertical velocity
                vert_vel = cumtrapz(fvert_acc, dx=dt, initial=0)

                # if using the optimal scale relationship, get the optimal scale
                if self.use_opt_scale:
                    coef_scale_original, _ = cwt(vert_vel, scale_original, 'gaus1')
                    F = abs(fft.rfft(coef_scale_original[0]))
                    # compute an estimate of the step frequency
                    step_freq = argmax(F) / vert_vel.size / dt

                    ic_opt_freq = 0.69 * step_freq + 0.34
                    fc_opt_freq = 3.6 * step_freq - 4.5

                    scale1 = round(0.4 / (2 * ic_opt_freq * dt)) - 1
                    scale2 = round(0.4 / (2 * fc_opt_freq * dt)) - 1
                else:
                    scale1 = scale2 = scale_original

                coef1, _ = cwt(vert_vel, scale1, 'gaus1')
                """
                Find the local minima in the signal. This should technically always require using 
                the negative signal in "find_peaks", however the way PyWavelets computes the
                CWT results in the opposite signal that we want.
                Therefore, if the sign of the acceleration was negative, we need to use the
                positve coefficient signal, and opposite for positive acceleration reading.
                """
                ic, *_ = find_peaks(-sign(acc_mean[v_axis]) * coef1[0],
                                    height=0.5*std(coef1[scale1]))

                coef2, _ = cwt(coef1[scale2], scale2, 'gaus1')

                """
                Peaks are the final contact points
                Same issue as above
                """
                fc, *_ = find_peaks(-sign(acc_mean[v_axis]) * coef2[0], height=0.5 * std(coef2[0]))

                # add the starting index so events are absolute index
                ic += bstart
                fc += bstart

                # GET STEPS/STRIDES/ETC
                # ======================================
                loading_forward_time = self.loading_factor * self.max_stride_time
                stance_forward_time = (self.max_stride_time / 2) + loading_forward_time

                # create sample times for events
                ic_times = ic * dt
                fc_times = fc * dt

                sib = 0  # steps in bout
                for i, curr_ic in enumerate(ic_times):
                    fc_forward = fc[fc_times > curr_ic]
                    fc_forward_times = fc_times[fc_times > curr_ic]

                    # OPTIMIZATION 1: initial double support (loading) time should be less than
                    # max_stride_time * loading_factor
                    if (fc_forward_times < (curr_ic + loading_forward_time)).sum() != 1:
                        continue  # skip this IC
                    # OPTIMIZATION 2: stance time should be less than half a gait cycle
                    # + initial double support time
                    if (fc_forward_times < (curr_ic + stance_forward_time)).sum() < 2:
                        continue  # skip this ic

                    # if this point is reached, both optimizations passed
                    gait['IC'].append(ic[i])
                    gait['FC'].append(fc_forward[1])
                    gait['FC opp foot'].append(fc_forward[0])
                    sib += 1

                if sib > 2:
                    gait['b valid cycle'].extend(
                        [((gait['IC'][ig + i+2] - gait['IC'][ig + i]) * dt) < self.max_stride_time
                         for i in range(sib-2)]
                    )
                if sib > 0:
                    gait['b valid cycle'].extend([False] * sib)

                # GET GAIT METRICS
                # ======================================
                # compute the vertical position
                vert_pos = cumtrapz(vert_vel, dx=dt, initial=0)

                # get the change in height
                for i in range(sib - 1):
                    if gait['b valid cycle'][ig + i]:
                        i1 = gait['IC'][ig+i] - bstart
                        i2 = gait['IC'][ig+i+1] - bstart
                        gait['delta h'].append(
                            (vert_pos[i1:i2].max() - vert_pos[i1:i2].min()) * 9.81  # convert to m
                        )
                    else:
                        gait['delta h'].append(nan)

                # regularity metrics
                for i in range(sib - 1):
                    i1 = gait['IC'][i] - bstart
                    i2 = gait['IC'][i + 1] - bstart
                    i3 = 2 * gait['IC'][i + 1] - gait['IC'][i] - bstart
                    if i3 < vert_acc.size:
                        gait['PARAM:step regularity - V'].append(
                            self._autocov(vert_acc, i1, i2, i3))

                for i in range(sib - 2):
                    i1 = gait['IC'][i] - bstart
                    i2 = gait['IC'][i + 2] - bstart
                    i3 = 2 * gait['IC'][i + 2] - gait['IC'][i] - bstart

                    if i3 < vert_acc.size:
                        gait['PARAM:stride regularity - V'].append(
                            self._autocov(vert_acc, i1, i2, i3))

                # per bout metrics
                gait['Bout N'].extend([ibout+1] * sib)
                gait['Bout Start'].extend(time[start+bout[0]] * sib)
                gait['Bout Duration'].extend([(bout[1] - bout[0]) * dt] * sib)
                gait['Bout Steps'].extend([sum(gait['b valid cycle'][ig:])] * sib)

                ig += sib

            # add the day number
            gait['Day N'].extend([iday+1] * (len(gait['Bout N']) - len(gait['Day N'])))

        # convert to arrays
        for key in gait:
            gait[key] = array(gait[key])

        # create the parameters
        for p in self.params:
            gait[f'PARAM:{p}'] = full(gait['IC'].size, nan, dtype=float_)
        for p in self.asym_params:
            gait[f'PARAM:{p} asymmetry'] = full(gait['IC'].size, nan, dtype=float_)

        # compute step length first because needed by stride length
        if height is not None:
            gait['PARAM:step length'] = 2 * sqrt(
                2 * leg_length * gait['delta h'] - gait['delta h']**2)

        # compute additional gait metrics - only some need to be computed per bout
        for day in unique(gait['Day N']):
            for bout in unique(gait['Bout N'][gait['Day N'] == day]):
                mask = (gait['Day N'] == day) & (gait['Bout N'] == bout)

                gait['PARAM:stride time'][mask][:-2] = (gait['IC'][mask][2:]
                                                        - gait['IC'][mask][:-2]) * dt
                gait['Param:swing time'][mask][:-2] = (gait['IC'][mask][2:]
                                                       - gait['FC'][:-2]) * dt
                gait['PARAM:step time'][mask][:-1] = (gait['IC'][mask][1:]
                                                      - gait['IC'][mask][:-1]) * dt
                gait['PARAM:terminal double support'][mask][:-1] = (gait['FC opp foot'][mask][1:]
                                                                    - gait['IC'][mask][1:]) * dt
                gait['PARAM:single support'][mask][:-1] = (gait['IC'][mask][1:]
                                                           - gait['FC opp foot'][mask][:-1]) * dt
                if height is not None:
                    gait['PARAM:stride length'][mask][:-1] = gait['PARAM:step length'][mask][:-1] \
                                                             + gait['PARAM:step length'][mask][1:]

        # compute rest of metrics that can be computed all at once
        gait['PARAM:stance time'][:] = (gait['FC'] - gait['IC']) * dt
        gait['PARAM:initial double support'][:] = (gait['FC opp foot'] - gait['IC']) * dt
        gait['PARAM:double support'][:] = gait['PARAM:initial double support'] \
                                          + gait['PARAM:terminal double support']

        if height is not None:
            gait['PARAM:gait speed'][:] = gait['PARAM:stride length'] / gait['PARAM:stride time']

        gait['PARAM:cadence'][:] = 60 / gait['PARAM:step time']

        # compute basic asymmetry parameters
        for day in unique(gait['Day N']):
            for bout in unique(gait['Bout N'][gait['Day N'] == day]):
                mask = (gait['Day N'] == day) & (gait['Bout N'] == bout)
                for p in ['stride time', 'stance time', 'swing time', 'step time',
                          'initial double support', 'terminal double support', 'double support',
                          'single support', 'step length', 'stride length']:
                    gait[f'PARAM:{p} asymmetry'][mask][:-1] = abs(gait[f'PARAM:{p}'][mask][1:]
                                                                  - gait[f'PARAM:{p}'][mask][:-1])

        gait['PARAM:autocorrelation symmetry - V'] = abs(
            gait['PARAM:step regularity - V'] - gait['PARAM:stride regularity - V'])

        kwargs.update({self._acc: accel, self._time: time, self._gyro: gyro, 'height': height})
        return kwargs, gait

    @staticmethod
    def _autocov(x, i1, i2, i3):
        ac = cov(x[i1:i2], x[i2:i3], bias=False)[0, 1]
        return ac / (std(x[i1:i2], ddof=1) * std(x[i2:i3], ddof=1))

    def _get_gait_bouts(self, classification, dt):
        """
        Get the gait bouts from an array of per sample predictions of gait

        Parameters
        ----------
        classification : numpy.ndarray
            Array of predictions of gait

        Returns
        -------
        bouts : numpy.ndarray
            (M, 2) array of starts and stops of gait bouts
        """
        starts = where(diff(classification.astype(int)) == 1)[0]
        stops = where(diff(classification.astype(int)) == -1)[0]

        if classification[0]:
            starts = insert(starts, 0, 0)
        if classification[-1]:
            stops = append(stops, len(classification) - 1)

        if starts.size != stops.size:
            raise ValueError('Starts and stops of bouts do not match')

        bouts = []
        nb = 0
        while nb < starts.size:
            ncb = 0
            while ((starts[nb+ncb+1] - stops[nb+ncb]) * dt) < self.max_bout_sep:
                ncb += 1

            if ((stops[nb+ncb] - starts[nb]) * dt) > self.min_bout:
                bouts.append((starts[nb], stops[nb+ncb]))

            nb += ncb + 1

        return bouts
