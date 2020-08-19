"""Functions defined on the unit hypercube for the purpose of integration tests"""
from numbers import Number
import torch
import numpy as np
from scipy.special import gamma
from math import pi
from better_abc import ABC, abstractmethod


def sanitize_variable(x, device=None):
    """Prepare input variable for a pytorch function:
    if it is a python numerical variable or a numpy array, then cast it to a tensor
    if it is is a tensor, make a copy to make sure the function cannot be altered from outside

    Parameters
    ----------
    x: float or np.ndarray or torch.Tensor
    device: None or torch.device

    Returns
    -------
        torch.Tensor

    """
    if isinstance(x, Number) or isinstance(x, np.ndarray):
        if device is None:
            device = torch.device("cpu")
        x = torch.tensor(x).to(device)
    else:
        assert isinstance(x, torch.Tensor), "Only numerical types, numpy arrays and torch Tensor accepted"
        x = x.clone().detach()
        if device is not None:
            x = x.to(device)
    return x


class Integrand(ABC):
    """Abstract class to define integrands for testing the integration library"""

    def __init__(self, d):
        self.d = d

    @abstractmethod
    def evaluate_integrand(self, x):
        """Compute the value of the integrand on a batch of points"""

    def __call__(self, x):
        """Compute the value of the integrand on a batch of points"""
        assert len(x.shape) == 2, f"Shape mismatch, expected (*, {self.d})"
        assert x.shape[1] == self.d, f"Shape mismatch, expected (*, {self.d})"
        return self.evaluate_integrand(x)


class KnownIntegrand(Integrand, ABC):
    """Abstract class for integrands with a known integral value"""

    @abstractmethod
    def integral(self):
        """Compute the true value of the integral"""

    def compare_absolute(self, estimated_integral):
        """Compute the absolute difference between an integral and the true value"""
        return abs(self.integral() - estimated_integral)

    def compare_relative(self, estimated_integral):
        """Compute the relative difference between an integral estimation and the true value"""
        return self.compare_absolute(estimated_integral) / (0.5 * (abs(self.integral()) + abs(estimated_integral)))

    def check(self, estimated_integral, tolerance=1.e-3, method="relative"):
        """Check the value of an estimation of the integral value

        Parameters
        ----------
        estimated_integral: float
        tolerance: float
        method: {"relative", "absolute"}

        Returns
        -------
            bool
        """
        if method == "relative":
            return self.compare_relative(estimated_integral) <= tolerance
        elif method == "absolute":
            return self.compare_absolute(estimated_integral) <= tolerance
        else:
            raise ValueError("Only accepted methods are 'relative' and 'absolute")


class VolumeIntegrand(Integrand, ABC):
    """Abstract class to define integrands that are 1 on a characteristic subspace and 0 outside, defined
    through an inequality f(x) >= 0"""

    @abstractmethod
    def inequality(self, x):
        """The characteristic inequality of the volume we want to measure

        Parameters
        ----------
        x: torch.Tensor

        Returns
        -------
            torch.BoolTensor
        """

    def evaluate_integrand(self, x):
        """Compute the value of the integrand on a batch of points by checking their inequality
        Parameters
        ----------
        x: torch.Tensor

        Returns
        -------
            torch.Tensor
        """
        return self.inequality(x).to(x.dtype)


class HyperrectangleVolumeIntegrand(VolumeIntegrand, KnownIntegrand):
    """Characteristic function of an hyperrectangle defined by cutting the
    unit hypercube along one axis. Its characteristic inequality is x[i] <= frac
    where 0. < frac < 1.
    """

    def __init__(self, d, split_dim=0, frac=0.5):
        """

        Parameters
        ----------
        d: int
        split_dim: int
        frac: float
        """
        super(HyperrectangleVolumeIntegrand, self).__init__(d=d)
        assert 0 <= split_dim < d
        assert 0. <= frac <= 1.

        self.split_dim = split_dim
        self.frac = frac

    def integral(self):
        """The integral is the length of the non-unit side of the hyperrectangle"""
        return self.frac

    def inequality(self, x):
        """Check if we are in the hyperrectangle"""
        return x[:, self.split_dim] < self.frac


class HypersphereVolumeIntegrand(VolumeIntegrand, KnownIntegrand):
    """Characteristic function of an hypersphere. The hypersphere must fit in the unit hypercube fully"""

    def __init__(self, d, r, c, device=None):
        """

        Parameters
        ----------
        d: int
        r: float
        c: torch.Tensor or float
        """
        super(HypersphereVolumeIntegrand, self).__init__(d=d)
        self.r = r
        self.c = sanitize_variable(c, device=device)

        assert (self.r > 0), "The radius must be positive"
        assert len(self.c.shape) == 0 or tuple(self.c.shape) == (d,), "The center is either a number or a d-vector"
        assert ((self.c - self.r) > 0.).all().item() and \
               ((self.c + self.r) < 1.).all().item(), "The full hypersphere must fit in the unit hypercube"

    def inequality(self, x):
        """Check if the points are in the hypersphere"""
        return ((x - self.c) ** 2).sum(dim=1).sqrt() <= self.r

    def integral(self):
        """Compute the volume of the hypersphere in d dimensions"""
        return float((self.r ** self.d) * (pi ** (self.d / 2.)) / gamma(self.d / 2.+1))


class DiagonalGaussianIntegrand(Integrand):
    """N-dimensional gaussian with a diagonal covariance matrix"""

    def __init__(self, d, mu=0.5, s=0.1, norm=1., device=None):
        """

        Parameters
        ----------
        mu : float or torch.Tensor
            Mean of the gaussian. Either a scalar or a vector of size d
        s: float or torch.Tensor
            Standard deviation of the gaussian. Either a scalar or a vector of size d
        norm: float or torch.Tensor
            Prefactor of the gaussian. Must be a scalar.
        device: torch.device
            Default device where the parameters are stored
        """
        super(DiagonalGaussianIntegrand, self).__init__(d)
        self.mu = sanitize_variable(mu, device)
        self.s = sanitize_variable(s, device)
        self.norm = sanitize_variable(norm, device)
        self.default_device = device

        assert len(self.mu.shape) == 0 or tuple(self.mu.shape) == (d,)
        assert len(self.s.shape) == 0 or tuple(self.s.shape) == (d,)
        assert len(self.norm.shape) == 0

    def evaluate_integrand(self, x):
        """Compute the gaussian

        The parameters of the gaussian are sent to the device of the input

        Parameters
        ----------
        x: torch.Tensor
            Batch of points of size (*,d)

        Returns
        -------
            torch.Tensor
        """
        return self.norm * torch.exp(-((x - self.mu.to(x.device)) / self.s.to(x.device)).square().sum(axis=1))


class CamelIntegrand(Integrand):
    """Camel function: two gaussian peaks on the hyperdiagonal of the unit hypercube
    at points (0.25, ..., 0.25) and (0.75, ..., 0.75).
    """

    def __init__(self, d, s1=0.1, norm1=1, s2=0.2, norm2=2, device=None):
        """
        Parameters
        ----------
        s1: float or torch.Tensor
            std of the first gaussian. Either a scalar or a vector of size d
        s2: float or torch.Tensor
            std of the second gaussian. Either a scalar or a vector of size d
        norm1: float or torch.Tensor
            normalization of the first gaussian. Must be a scalar.
        norm2: float or torch.Tensor
            normalization of the second gaussian. Must be a scalar.
        device: default device on which to run the computation
        """
        super(CamelIntegrand, self).__init__(d)
        self.s1 = sanitize_variable(s1, device)
        self.norm1 = sanitize_variable(norm1, device)
        self.s2 = sanitize_variable(s2, device)
        self.norm2 = sanitize_variable(norm2, device)
        self.default_device = device

        self.hump1 = DiagonalGaussianIntegrand(d, 0.25, s1, norm1, device)
        self.hump2 = DiagonalGaussianIntegrand(d, 0.75, s2, norm2, device)

    def evaluate_integrand(self, x):
        """Compute the camel function for a batch of points

        Parameters
        ----------
        x: torch.Tensor

        Returns
        -------
        torch.Tensor
        """
        return self.hump1.evaluate_integrand(x)+self.hump2.evaluate_integrand(x)
