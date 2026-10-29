"""Differentiable IndPenSim model in JAX (the ``jax`` extra, or ``pip install jax``).

    from penicillium import jax_model

    dy = jax_model.rhs(t, y, par)  # same as penicillium.model.rhs, as a JAX array
    J = jax_model.state_jacobian(t, y, par)  # exact d(dy/dt)/dy, 33 x 33
    S = jax_model.parameter_jacobian(t, y, par)  # exact d(dy/dt)/d(par), 33 x 31

The JAX function is generated at import time from the source of ``model.rhs_into``, the function the Python and
Numba backends run, so the three cannot drift apart: ``math`` becomes ``jax.numpy``, conditional expressions and
``if`` blocks become ``jnp.where`` selections between both branches. Everything is jit-compiled, works with
``vmap``, and is differentiable with respect to the state, the inputs and the parameters (``PARAM_NAMES``).

Uses: exact Jacobians for implicit solvers and stability analysis, linearisations for MPC and extended Kalman
filters, parameter sensitivities, and gradients through user-written integrators. Importing this module enables
JAX's 64-bit mode (``jax_enable_x64``), which the model needs.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

try:
    import jax
    import jax.numpy as jnp
except ImportError as exc:  # pragma: no cover - exercised without the extra
    raise ImportError("penicillium.jax_model needs JAX: pip install jax") from exc

from . import model
from .model import N_PARAMS, N_STATES, PARAM_NAMES, STATE_NAMES

jax.config.update("jax_enable_x64", True)

__all__ = ["N_PARAMS", "N_STATES", "PARAM_NAMES", "STATE_NAMES", "parameter_jacobian", "rhs", "state_jacobian"]


class _ToJax(ast.NodeTransformer):
    """Rewrite ``rhs_into`` into branch-free code: both sides of every condition are computed and selected.

    An ``if`` block becomes: ``_cN = <test>``; for each branch, a copy of every variable (or ``dy[i]``) the block
    assigns, starting from its current value; the branch body working on those copies; finally
    ``x = jnp.where(_cN, <copy of the true branch>, <copy of the false branch>)`` for each of them.
    """

    def __init__(self) -> None:
        self.counter = 0  # numbers the if blocks, to name their temporaries
        self.defined: set[str] = set()  # variables assigned so far (others start a branch at 0.0)

    def visit_Attribute(self, node: ast.Attribute):  # math.xxx -> jnp.xxx
        self.generic_visit(node)
        if isinstance(node.value, ast.Name) and node.value.id == "math":
            node.value = ast.Name("jnp", ast.Load())
        return node

    def visit_IfExp(self, node: ast.IfExp):  # a if c else b -> jnp.where(c, a, b)
        self.generic_visit(node)
        return ast.Call(ast.parse("jnp.where", mode="eval").body, [node.test, node.body, node.orelse], [])

    def visit_Assign(self, node: ast.Assign):
        self.generic_visit(node)
        self.defined |= {name for name in _assigned([node]) if not name.startswith("dy[")}
        return node

    visit_AugAssign = visit_Assign

    def visit_If(self, node: ast.If):
        self.counter += 1
        tag = self.counter
        cond = f"_c{tag}"
        test = self.visit(node.test)
        before = set(self.defined)
        branches = {"t": [self.visit(s) for s in node.body], "f": [self.visit(s) for s in node.orelse]}
        assigned = sorted(_assigned(node.body) | _assigned(node.orelse))
        out: list[ast.stmt] = [ast.Assign([ast.Name(cond, ast.Store())], test, lineno=0)]
        for branch, stmts in branches.items():
            for name in assigned:
                start = name if (name in before or name.startswith("dy[")) else "0.0"
                out.append(_parse(f"{_temp(name, branch, tag)} = {start}"))
            renamer = _Rename({name: _temp(name, branch, tag) for name in assigned})
            for stmt in stmts:  # a nested if was already expanded into a list of statements
                out.extend(renamer.visit(s) for s in (stmt if isinstance(stmt, list) else [stmt]))
        for name in assigned:
            out.append(_parse(f"{name} = jnp.where({cond}, {_temp(name, 't', tag)}, {_temp(name, 'f', tag)})"))
            if not name.startswith("dy["):
                self.defined.add(name)
        return out


class _Rename(ast.NodeTransformer):
    """Rename variables (and constant-index ``dy[i]`` targets) to branch-local temporaries."""

    def __init__(self, mapping: dict[str, str]) -> None:
        self.mapping = mapping

    def visit_Name(self, node: ast.Name):
        if node.id in self.mapping:
            return ast.copy_location(ast.Name(self.mapping[node.id], node.ctx), node)
        return node

    def visit_Subscript(self, node: ast.Subscript):
        key = _dy_key(node)
        if key in self.mapping:
            return ast.copy_location(ast.Name(self.mapping[key], node.ctx), node)
        self.generic_visit(node)
        return node


def _dy_key(node: ast.AST) -> str | None:
    """``"dy[i]"`` for a subscript ``dy[i]`` with a constant ``i``, else ``None``."""
    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "dy"
        and isinstance(node.slice, ast.Constant)
    ):
        return f"dy[{node.slice.value}]"
    return None


def _assigned(stmts: list[ast.stmt]) -> set[str]:
    """Variables and ``dy[i]`` entries assigned anywhere in ``stmts`` (including tuple targets)."""
    names: set[str] = set()
    for node in (n for stmt in stmts for n in ast.walk(stmt)):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AugAssign):
            targets = [node.target]
        else:
            continue
        for target in targets:
            for t in target.elts if isinstance(target, ast.Tuple) else [target]:
                if isinstance(t, ast.Name):
                    names.add(t.id)
                elif (key := _dy_key(t)) is not None:
                    names.add(key)
    return names


def _temp(name: str, branch: str, tag: int) -> str:
    return f"_{branch}{tag}_" + name.replace("[", "_").replace("]", "")


def _parse(code: str) -> ast.stmt:
    return ast.parse(code).body[0]


def _build_rhs_into():
    tree = ast.parse(textwrap.dedent(inspect.getsource(model.rhs_into)))
    func = tree.body[0]
    func.name = "_rhs_into_jax"
    func.body = _ToJax().visit(ast.Module(body=func.body, type_ignores=[])).body
    tree = ast.fix_missing_locations(tree)
    namespace = {"jnp": jnp}
    exec(compile(tree, "<penicillium.jax_model>", "exec"), namespace)
    return namespace["_rhs_into_jax"], ast.unparse(tree)


#: The generated function, and its source (``print(jax_model.GENERATED_SOURCE)`` to review the transform).
_rhs_into_jax, GENERATED_SOURCE = _build_rhs_into()


@jax.jit
def rhs(t, y, par):
    """Time derivative of the IndPenSim state (``model.rhs``) as a JAX array."""
    dy = [jnp.zeros((), dtype=jnp.float64) for _ in range(N_STATES)]
    _rhs_into_jax(t, y, par, dy)
    return jnp.stack([jnp.asarray(v, dtype=jnp.float64) for v in dy])


#: Exact Jacobian of ``rhs`` with respect to the state, shape (33, 33).
state_jacobian = jax.jit(jax.jacfwd(rhs, argnums=1))

#: Exact Jacobian of ``rhs`` with respect to the parameters and inputs (``PARAM_NAMES``), shape (33, 31).
parameter_jacobian = jax.jit(jax.jacfwd(rhs, argnums=2))
