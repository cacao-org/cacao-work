"""Attribute the 2SLS gain estimate to the physical components of B, per instrument set."""
import numpy as np
from sim import simulate
import estimators as E

res = {}
for seed in (301, 302, 303, 304):
    sim = simulate(seed, sig_nA=0.002, sig_nB=0.002, c_hi=0.6); g = sim["gB"]; c = sim["comp"]
    names = ("phi", "u", "dm", "n")
    Ae, Be, De, *cs = E.sync_exact(sim, extra=[c[k] for k in names])
    comps = dict(zip(names, cs))
    nA, nB = len(sim["tA"]), len(sim["tB"])
    idx = np.arange(nA)[3 : min(nA, nB // 2) - 3]
    C1 = sim["C1"][idx, :40]; C1 = C1 - C1.mean(0)
    tle = E.est_tool(Ae, Be, De)
    Bc, Dc, Ac = Be - Be.mean(0), De - De.mean(0), Ae - Ae.mean(0)
    Saa = Ac.T @ Ac
    psi = Ac @ np.linalg.solve(Saa + 1e-2 * np.diag(np.diag(Saa)), Ac.T @ (Bc - Dc @ tle["Mdb"].T))
    N = len(Bc); t = np.arange(9, N)
    sets = {"psi8": lambda i: [psi[t - l, i] for l in range(1, 9)],
            "psi8+c1": lambda i: ([psi[t - l, i] for l in range(1, 9)]
                                  + [C1[t - l, i] for l in (1, 2)]),
            "psi8+c1(3,4)": lambda i: ([psi[t - l, i] for l in range(1, 9)]
                                       + [C1[t - l, i] for l in (3, 4)]),
            "psi8+dC1": lambda i: ([psi[t - l, i] for l in range(1, 9)]
                                   + [C1[t - 1, i] - C1[t - 2, i]])}
    for nm, f in sets.items():
        acc = res.setdefault(nm, {k: [] for k in names + ("total", "r2psi", "r2d", "cond")})
        tot = np.zeros(40)
        parts = {k: np.zeros(40) for k in names}
        r2p = np.zeros(40)
        r2d = np.zeros(40)
        cn = np.zeros(40)
        for i in range(40):
            Z = np.column_stack(f(i)); Q, _ = np.linalg.qr(Z)
            X = np.column_stack([psi[t, i], Dc[t, i]]); Xh = Q @ (Q.T @ X)
            G = np.linalg.inv(Xh.T @ X)
            for k in names:
                y = comps[k][t, i] - comps[k][:, i].mean()
                parts[k][i] = (G @ (Xh.T @ y))[1] / g[i]
            tot[i] = (G @ (Xh.T @ Bc[t, i]))[1] / g[i]
            r2p[i] = (Xh[:, 0] @ Xh[:, 0]) / (X[:, 0] @ X[:, 0])
            r2d[i] = (Xh[:, 1] @ Xh[:, 1]) / (X[:, 1] @ X[:, 1])
            cn[i] = np.linalg.cond(Xh.T @ Xh / np.outer(np.sqrt(np.diag(Xh.T @ Xh)),
                                                        np.sqrt(np.diag(Xh.T @ Xh))))
        for k in names:
            acc[k].append(np.median(parts[k][4:]))
        acc["total"].append(np.median(tot[4:]))
        acc["r2psi"].append(np.median(r2p[4:]))
        acc["r2d"].append(np.median(r2d[4:]))
        acc["cond"].append(np.median(cn[4:]))
print("instrument set      total | from DM term  from phi term  from B-only u"
      "  from WFS-B noise | 1st-stage R2: psi   D | cond(Xh)")
for nm, a in res.items():
    m = {k: float(np.mean(v)) for k, v in a.items()}
    print(f"{nm:16s}  {m['total']:+6.2f} |   {m['dm']:+6.2f}       {m['phi']:+6.2f}"
          f"        {m['u']:+6.2f}         {m['n']:+6.2f}      |"
          f"        {m['r2psi']:.3f} {m['r2d']:.3f} | {m['cond']:.0f}")
