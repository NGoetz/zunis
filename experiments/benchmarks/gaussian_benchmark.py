"""Comparing ZuNIS to VEGAS on gaussian integrals (VEGAS expected to be better)"""

import vegas
from functools import partial
import pandas as pd
import torch
from utils.integrands.gaussian import DiagonalGaussianIntegrand
from utils.logging import get_benchmark_logger, get_benchmark_logger_debug
from utils.torch_utils import get_device
from utils.integrator_integrals import IntegratorSampler
from zunis.integration import Integrator

#############################################################
#       DEBUG FLAG: set to False to log and save to file
#############################################################
debug = True
#############################################################


if debug:
    logger = get_benchmark_logger_debug("benchmark_hypercamel")
else:
    logger = get_benchmark_logger("benchmark_hypercamel")

device = get_device(cuda_ID=0)

gaussian = DiagonalGaussianIntegrand(d=2, device=device)

@vegas.batchintegrand
def vgaussian(x):
    return gaussian(torch.tensor(x).to(device)).cpu()


integrator = Integrator(d=2, f=gaussian, device=device)
vintegrator = vegas.Integrator([[0, 1], [0, 1]])

integrator_sampler = IntegratorSampler(integrator, survey_args={"n_batch":100000})

vintegrator(vgaussian, nitn=10, neval=100000)
