from .integratorAPI import SurveyRefineIntegratorAPI
import pandas as pd
import numpy as np
import torch
import logging

# TODO: change where the method we use from this class is
from zunis.training.weighted_dataset.weighted_dataset_trainer import BasicStatefulTrainer, BasicTrainer
from zunis.models.flows.sampling import UniformSampler


class PosteriorSurveySamplingIntegrator(SurveyRefineIntegratorAPI):
    """Most basic integrator:
    Takes a trainer object at initialization and samples from a given distribution in target space
    during the survey phase. The function to integrate is given at initialization.
    """

    @staticmethod
    def empty_history():
        """Create an empty history object"""
        return pd.DataFrame({
            "integral": pd.Series([], dtype="float"),
            "error": pd.Series([], dtype="float"),
            "n_points": pd.Series([], dtype="int"),
            "phase": pd.Series([], dtype="str")
        })

    def __init__(self, f, trainer, posterior, n_iter=10, n_iter_survey=None, n_iter_refine=None,
                 n_points=100000, n_points_survey=None, n_points_refine=None, use_survey=False,
                 verbosity=None, trainer_verbosity=None,  **kwargs):
        super(PosteriorSurveySamplingIntegrator, self).__init__(verbosity=verbosity, **kwargs)
        self.f = f

        assert isinstance(trainer, BasicTrainer), "This integrator relies on the BasicTrainer API"

        self.model_trainer = trainer
        self.posterior = posterior

        self.model_trainer.set_verbosity(trainer_verbosity)

        self.n_iter_survey = n_iter_survey if n_iter_survey is not None else n_iter
        self.n_iter_refine = n_iter_refine if n_iter_refine is not None else n_iter
        self.n_points_survey = n_points_survey if n_points_survey is not None else n_points
        self.n_points_refine = n_points_refine if n_points_refine is not None else n_points

        self.use_survey = use_survey

        self.integration_history = self.empty_history()

    def initialize(self, **kwargs):
        self.integration_history = self.empty_history()

    def initialize_survey(self, **kwargs):
        pass

    def initialize_refine(self, **kwargs):
        pass

    def sample_survey(self, *, n_points=None, f=None, **kwargs):
        """Sample points from target space distribution"""
        # TODO, change where this method is /!\
        if n_points is None:
            n_points = self.n_points_survey
        if f is None:
            f = self.f
        return BasicStatefulTrainer.generate_target_batch_from_posterior(n_points, f, self.posterior)

    def sample_refine(self, *, n_points=None, f=None, **kwargs):
        if n_points is None:
            n_points = self.n_points_refine
        if f is None:
            f = self.f

        xj = self.model_trainer.sample_forward(n_points)
        x = xj[:, :-1]
        px = torch.exp(-xj[:, -1])
        fx = f(x)

        return x, px, fx

    def process_survey_step(self, sample, integral, integral_var, training_record, **kwargs):
        x, px, fx = sample
        n_points = x.shape[0]
        self.integration_history = self.integration_history.append(
            {"integral": integral,
             "error": (integral_var / n_points) ** 0.5,
             "n_points": n_points,
             "phase": "survey",
             "training record": training_record},
            ignore_index=True
        )
        self.logger.info(f"Integral: {integral:.3e} +/- {(integral_var / n_points) ** 0.5:.3e}")

    def process_refine_step(self, sample, integral, integral_var, **kwargs):
        x, px, fx = sample
        n_points = x.shape[0]
        self.integration_history = self.integration_history.append(
            {"integral": integral,
             "error": (integral_var / n_points) ** 0.5,
             "n_points": n_points,
             "phase": "refine"},
            ignore_index=True
        )

        self.logger.info(f"Integral: {integral:.3e} +/- {(integral_var / n_points) ** 0.5:.3e}")

    def finalize_survey(self, **kwargs):
        pass

    def finalize_refine(self, **kwargs):
        pass

    def finalize_integration(self, use_survey=None, **kwargs):
        if use_survey is None:
            use_survey = self.use_survey

        if use_survey:
            data = self.integration_history
        else:
            data = self.integration_history.loc[self.integration_history["phase"] == "refine"]

        result = (data["integral"] * data["n_points"]).sum()
        result /= data["n_points"].sum()

        error = np.sqrt(((data["error"] * data["n_points"]) ** 2).sum() / (data["n_points"].sum()) ** 2)

        self.logger.info(f"Final result: {float(result):.5e} +/- {float(error):.5e}")

        return float(result), float(error), self.integration_history


class FlatSurveySamplingIntegrator(PosteriorSurveySamplingIntegrator):
    def __init__(self, f, trainer, d, n_iter=10, n_iter_survey=None, n_iter_refine=None,
                 n_points=100000, n_points_survey=None, n_points_refine=None, use_survey=False,
                 device=torch.device("cpu"), verbosity=2, trainer_verbosity=1, **kwargs):
        posterior = UniformSampler(d=d, device=device)
        super(FlatSurveySamplingIntegrator, self).__init__(f=f,
                                                           trainer=trainer,
                                                           d=d,
                                                           posterior=posterior,
                                                           n_iter=n_iter,
                                                           n_iter_survey=n_iter_survey,
                                                           n_iter_refine=n_iter_refine,
                                                           n_points=n_points,
                                                           n_points_survey=n_points_survey,
                                                           n_points_refine=n_points_refine,
                                                           use_survey=use_survey,
                                                           verbosity=verbosity,
                                                           trainer_verbosity=trainer_verbosity,
                                                           **kwargs)
        self.d = d