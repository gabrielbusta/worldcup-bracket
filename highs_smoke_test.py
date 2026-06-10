import pyomo.environ as pyo

# Mini advancement-style MIP: pick which teams "reach" a round to max EV,
# one-per-match constraint. Mirrors the real model's shape.
m = pyo.ConcreteModel()
teams = ['A','B','C','D']            # two R32 matches: (A,B) and (C,D)
ev = {'A':9.0,'B':4.0,'C':5.0,'D':8.0}   # ADV_PTS * P_real(reach R16)
m.T = pyo.Set(initialize=teams)
m.reach = pyo.Var(m.T, domain=pyo.Binary)

# exactly one advances from each match
m.match1 = pyo.Constraint(expr=m.reach['A'] + m.reach['B'] == 1)
m.match2 = pyo.Constraint(expr=m.reach['C'] + m.reach['D'] == 1)
m.obj = pyo.Objective(expr=sum(ev[t]*m.reach[t] for t in m.T), sense=pyo.maximize)

SOLVER = pyo.SolverFactory("appsi_highs")
print("available:", SOLVER.available())
res = SOLVER.solve(m)
print("termination:", res.solver.termination_condition)
print("advance:", [t for t in teams if pyo.value(m.reach[t])>0.5], "EV:", pyo.value(m.obj))
