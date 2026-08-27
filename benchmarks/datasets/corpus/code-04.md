# Numerical Recipes

Small numeric kernels used by the scoring service.

## Softmax

```python
import math


def softmax(values: list[float]) -> list[float]:
    peak = max(values)
    exps = [math.exp(v - peak) for v in values]
    total = sum(exps)
    return [e / total for e in exps]
```

## Log-Sum-Exp

```python
def log_sum_exp(values: list[float]) -> float:
    peak = max(values)
    return peak + math.log(sum(math.exp(v - peak) for v in values))
```

## Energy of a Signal

The energy of a sampled signal follows the classic relation:

$$E = \sum_{n=-\infty}^{\infty} |x[n]|^2$$

For a finite window, the same sum runs over the samples in the window.

## Distance Matrix

```python
def distances(points: list[tuple[float, float]]) -> list[list[float]]:
    matrix = [[0.0] * len(points) for _ in points]
    for i, (xi, yi) in enumerate(points):
        for j in range(i + 1, len(points)):
            xj, yj = points[j]
            d = math.hypot(xi - xj, yi - yj)
            matrix[i][j] = d
            matrix[j][i] = d
    return matrix
```

All kernels avoid intermediate overflow by subtracting the peak value before
exponentiating.
