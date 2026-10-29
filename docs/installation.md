# Installation

Penicillium needs **Python 3.10 or later**; it is tested in continuous integration on Linux, macOS and Windows
with Python 3.10 to 3.14. Its required
dependencies are NumPy, SciPy and pandas. Nothing needs compiling. If you have ever tried to build a C++ ODE
solver with Boost and OpenMP on a locked-down corporate laptop, you will appreciate that.

## Install from PyPI

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
pip install "penicillium[fast]"
```

## Install from the repository

To work on the code, or to run the case-study notebooks, benchmarks and validation scripts, install it from a
clone of the repository:

```bash
git clone https://github.com/francesco-sartori/Penicillium.git
cd Penicillium
pip install -e ".[fast]"
```

## Optional extras

Extras add features on top of the core simulator. Combine them with commas: `pip install "penicillium[fast,gym]"`.

| Extra | Adds | You want it if... |
|---|---|---|
| `fast` | Numba | You want speed: about 20× faster batches. **Recommended.** |
| `parquet` | pyarrow | You save campaigns (`Campaign.save`) or use `penicillium generate` with Parquet output |
| `dcs` | FastAPI, uvicorn, Numba | You want the [operator console](dcs.md) in the browser (its front end ships prebuilt: Node.js is needed only to develop it) |
| `gym` | Gymnasium | You do [reinforcement learning](gymnasium.md) or use `scenarios.control_benchmark` |
| `minari` | Minari | You write offline-RL datasets |
| `jax` | JAX | You want the [differentiable model](differentiable.md) (Jacobians, gradients) |
| `notebooks` | matplotlib, scikit-learn, Jupyter kernel, plus `fast`, `parquet`, `minari` | You run the example notebooks |
| `all` | `fast`, `parquet`, `gym` | You want a sensible "everything for data work" install |
| `docs`, `test`, `dev` | Tooling | You build these pages or work on the code |

The examples in this documentation use matplotlib for plots. Install it with `pip install matplotlib` if you do
not use the `notebooks` extra.

## Check the installation

```python
import penicillium
from penicillium import Simulator

print(penicillium.__version__)
sim = Simulator()
print(sim.backend)  # "numba" with the fast extra, else "python"
result = sim.run(seed=1)
print(f"{len(result)} samples, {result.total_yield:.0f} kg")  # 1150 samples, about 3600 kg
```

!!! info "The first run is slower"
    With the `fast` extra, the first batch in a new environment spends a few seconds compiling the model with
    Numba. The compiled code is cached on disk, so later runs (and later Python sessions) start at full speed.
    This is a one-off cost, like commissioning a plant, only shorter.

## Choosing the backend

`Simulator(backend=...)` selects how the model equations are evaluated:

- `"auto"` (default): Numba if it is installed, otherwise pure Python.
- `"numba"`: compiled; about 0.6 s per 230 h batch. Raises `ImportError` if Numba is missing.
- `"python"`: pure Python; about 11 s per batch. Useful for debugging, or when Numba is unavailable on your
  platform.

The two backends agree to about 1e-11 (relative). The only differences come from the math libraries rounding
the last bits differently, so the choice affects speed, not results.
