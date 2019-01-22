import os,sys; sys.path.append(os.path.join((lambda r,f:f[0:f.index(r)+len(r)])('code',os.path.abspath(__file__)),'config')); import config
config.epimodel()
# epi-model imports
from space import *
from simulation import *
import outpututils
import initutils
import transmit
# external imports
import numpy as np

def dxfun(X,t,P,dxout={}):
  dX = X*0
  # births and deaths
  dX.update(P['nu']*P['pe']*X.sum(), hi='S', accum=np.add)
  dX.update(P['mu']*X, accum=np.subtract)
  # turnover
  if P['zeta'].space.dim('ii').n > 1:
    Xi = X.expand(Space(X.space.dims+[modelutils.partner(X.space.dim('ii'))]),norm=False)
    for ki in ['M','W']:
      XZk = Xi.iselect(ki=ki) * P['zeta'].iselect(ki=ki)
      dX.update(XZk.isum('ip'),ki=ki,accum=np.subtract)
      dX.update(XZk.isum('ii'),ki=ki,accum=np.add)
  # force of infection
  lam = transmit.lambda_fun(X,P['C'],P['beta'].islice(t=t),P['eps'],dxout)
  xlam = lam.isum('p').iselect(hi='S')*X.iselect(hi='S')
  transmit.transfer(dX, src={'hi':'S'}, dst={'hi':'I'}, N = xlam)
  # treatment
  transmit.transfer(dX, src={'hi':'I'}, dst={'hi':'T'}, N = X.iselect(hi='I') * P['tau'])
  # # full recovery -> for SIT model, we have no recovery
  # transmit.transfer(dX, src={'hi':'T'}, dst={'hi':'S'}, N = X.iselect(hi='T') * P['gamma'])
  # dxout
  dxout.update({'lam':locals()['lam']}) # TODO: what is going on here?
  # dxout.update({v:locals()[v] for v in dxout if v in locals()})
  # return
  return dX

def initfun(model,spaces):
  P = model.params
  # change rate
  P['C'].update(P['C-i'].expand(P['C'].space))
  # beta
  sbeta = spaces['super']
  P['beta'].update(P['beta-k'].expand(sbeta) * P['f-beta-h'].expand(sbeta))
  # turnover
  if P['zeta'].space.dim('ii').n > 1:
    for ki in ['M','W']:
      turnover = transmit.turnover(nu = P['nu'],
                                   mu = P['mu'],
                                   px = P['px'].islice(ki=ki),
                                   pe = P['pe'].islice(ki=ki),
                                   zeta = P['zeta'].islice(ki=ki),
                                   dur = P['dur'].islice(ki=ki),
                                   warn = True)
      P['zeta'].update(turnover['zeta'],ki=ki)
      P['dur'].update(turnover['dur'],ki=ki)
      P['pe'].update(turnover['pe'],ki=ki)
  # initial condition
  model.X0.update(P['N0']*P['px'],hi='S')

def infectfun(sim,N=1):
  sim.init_x(transmit.transfer(
    X = sim.X,
    src = {'hi':'S'},
    dst = {'hi':'I'},
    both = {'t':sim.t[0]},
    N = N))
  return sim

def get_targets(spaces,select,outputs,t=None,names=None):
  specdir = os.path.join(config.path['root'],'code','main','specs')
  targets = initutils.objs_from_json(initutils.make_target,
    os.path.join(specdir,'targets.json'),
    space = spaces['super'],
    select = select,
    outputs = outputs)
  names = [target.name for target in targets.values()] if names is None else flatten(names)
  return xdict(xfilter(targets.values(),name=names),ord=True)

def get_outputs(spaces,select,t,names=None,**kwargs):
  specs = {
    'N': {},
    'X': {},
    'prevalence': {'si':'infected'},
    'incidence': {'ss':'S'},
    'incidence-abs': {'ss':'S'},
    'cum-infect': {'ss':'S'},
    'tpaf-WH': {'beta':'beta','ss':'S'},
  }
  return xdict([
    outpututils.make_output(name,t=t,spaces=spaces,**specs[name])
    for name in names
  ])

def get_specs():
  specdir = os.path.join(config.path['root'],'code','main','specs')
  dims   = initutils.objs_from_json(Dimension,            os.path.join(specdir,'dimensions.json'))
  spaces = initutils.objs_from_json(initutils.make_space, os.path.join(specdir,'spaces.json'),dims=dims.values())
  params = initutils.objs_from_json(initutils.make_param, os.path.join(specdir,'params.json'),space=spaces['super'])
  accum  = initutils.objs_from_json(initutils.make_accum, os.path.join(specdir,'accumulators.json'),params=params)
  select = initutils.objs_from_json(Selector,             os.path.join(specdir,'selectors.json'))
  return {
    'dims': dims,
    'spaces': spaces,
    'params': params,
    'select': select,
    'accum': accum,
  }

def get_model():
  specs = get_specs()
  return Model(X0 = Array(0,specs['spaces']['index']),
               dxfun = dxfun,
               spaces = specs['spaces'],
               select = specs['select'],
               params = ParameterSet(specs['params'],accum=specs['accum']),
               initfun = lambda model: initfun(model,model.spaces))

def get_t(dt=0.5,tmin=0,tmax=200):
  return np.around(np.arange(tmin, tmax+1e-6, dt), 6)

def get_simulation(model,infect=True,outputs=[],t=None):
  infect = atleast(model.params['infect'],3) if 'infect' in model.params else \
           int(infect)
  t = t if t is not None else get_t()
  outputs = get_outputs(model.spaces,model.select,t=t,names=outputs)
  sim = Simulation(model,t,outputs=outputs)
  return infectfun(sim,N=infect)
