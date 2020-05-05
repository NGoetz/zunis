"""Trainable layers
"""
import torch

class OverallAffineLayer(torch.nn.Module):
    """Learnable overall affine transformation
    f(x) = alpha x + delta
    """

    def __init__(self, alpha=10., delta=0.):
        super().__init__()
        self.alpha = torch.nn.Parameter(torch.tensor(alpha), requires_grad=True)
        self.delta = torch.nn.Parameter(torch.tensor(delta), requires_grad=True)

    def forward(self, input):
        """Output of the OverallAffineLayer"""
        return input * self.alpha + self.delta


def create_rectangular_dnn(
        *,
        d_in,
        d_out,
        d_hidden,
        n_hidden,
        input_activation=None,
        hidden_activation=torch.nn.ReLU,
        output_activation=None,
        use_batch_norm=False):
        
        layers = []
        if input_activation is not None:
            layers.append(input_activation())
        layers.append(torch.nn.Linear(d_in,d_hidden))
        layers.append(hidden_activation())
        if use_batch_norm:
            layers.append(torch.nn.BatchNorm1d(d_hidden))

        for i in range(n_hidden):
            layers.append(torch.nn.Linear(d_hidden, d_hidden))
            layers.append(hidden_activation())
            if use_batch_norm:
                layers.append(torch.nn.BatchNorm1d(d_hidden))

        layers.append(torch.nn.Linear(d_hidden, d_out))

        if output_activation is not None:
            layers.append(output_activation())

        return torch.nn.Sequential(*layers)