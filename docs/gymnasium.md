# Reinforcement learning

Install the `gym` extra: `pip install "penicillium[fast,gym]"`.

```python
import gymnasium as gym

env = gym.make("penicillium.envs:IndPenSim-v0")
obs, info = env.reset(seed=0)
done = False
while not done:
    obs, reward, terminated, truncated, info = env.step(env.action_space.sample())
    done = terminated or truncated
print(info["total_yield_kg"])
```

| id | what changes |
|---|---|
| `IndPenSim-v0` | nominal batches |
| `IndPenSimFault-v0` | a random IndPenSim fault (or none) per episode; `info["fault"]`, `info["fault_active"]` |
| `IndPenSimRaman-v0` | `Dict` observation with the Raman spectrum |

**Options.** Keyword arguments of `gym.make("penicillium.envs:IndPenSim-v0", **options)`, the same for the three
environments:

| Option | Default | Meaning |
|---|---|---|
| `controlled` | `("Fs", "Foil", "Fg", "pressure", "Fw", "Fpaa")` | Inputs the agent sets: sugar, oil, aeration, pressure, water and PAA feeds; the others (and the broth draw) follow the recipe |
| `action_mode` | `"recipe_relative"` | Action `a` in [−1, 1] sets each input to recipe × (1 + `max_relative_change` · `a`), so `a = 0` is the recipe; `"absolute"`: the input values |
| `max_relative_change` | `0.5` | Largest relative change of an input in the relative mode (±50 %) |
| `observation` | `"measurements"` | Time and the online measurements; `"state"`: the 33 model states (for model-based methods) |
| `lab_measurements` | `False` | Add the latest lab results to the observation |
| `input_costs` | `None` | Cost per unit of each input and hour, subtracted from the reward |
| `solver_failure_reward` | `-100.0` | Reward of a step in which the solver fails (the episode ends) |
| `config`, `recipe` | IndPenSim defaults, without Raman spectra | [Configuration](configuration.md) and [recipe](control.md) of the batches |

**Episode.** One batch: 1150 steps of 12 minutes (or `config.batch_length_h`). The episode terminates at the end of
the batch, or if the solver fails (reward `solver_failure_reward`).

**Actions.** `action_mode="recipe_relative"` (default): `a` in `[-1, 1]` per controlled input scales the recipe value
by `1 + max_relative_change * a`; `a = 0` reproduces the recipe batch exactly. `action_mode="absolute"`: the input
values themselves. Controlled inputs default to sugar, oil, aeration, pressure, water and PAA feeds; the broth
discharge follows the recipe.

**Observations.** Time and the online measurements (`OBSERVATIONS`); `lab_measurements=True` adds the latest
off-line results; `observation="state"` gives the 33 model states instead (for model-based methods).

**Reward.** Penicillin harvested during the step (kg), minus `input_costs` per unit input and hour. The harvest of
a step is the change of the penicillin mass in the vessel, $\Phi = P V$, plus the penicillin removed by the draws
during the step, so the rewards of an episode add up to the batch yield. The reward is therefore already in the
form of potential-based shaping with the potential $\Phi = P V$ (Ng, Harada and Russell, 1999): it is dense (one
reward per 12-minute step), and it has the same return, and so the same optimal policy, as a single reward of the
batch yield at the end. Other shaped rewards, for example a penalty on PAA above the 2400 mg/L inhibition
threshold, change the optimal policy; they are left to you (wrap the environment, or use `input_costs`).

> A. Y. Ng, D. Harada, S. Russell. *Policy invariance under reward transformations: theory and application to
> reward shaping.* Proceedings of the 16th International Conference on Machine Learning (ICML 1999), 278–287.

**Seeding.** `reset(seed=...)` seeds the batch draw; `options={"batch_seed": n}` picks a batch directly and
`options={"fault": Fault.X}` a fault. The same seed always gives the same episode.

**Offline RL.** `penicillium.envs.collect_minari_dataset("penicillium/indpensim-recipe-v0", n_episodes=100)` writes a
Minari dataset (recipe policy with exploration noise by default); needs the `minari` extra (`pip install -e ".[minari]"`).
