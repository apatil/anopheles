# TODO: out_prob weighted by distance from EO region
# TODO: Add actual nugget, use Gibbs. Then can try additive, nonadditive versions easily.
# TODO: Constrain probability of presence 1500km outside EO region to low value.
# TODO: Then try Gibbs updates of full thing.

# import matplotlib
# matplotlib.use('pdf')
import anopheles
from anopheles_query import Session
from cov_prior import OrthogonalBasis, GivensStepper
from pymc import AdaptiveMetropolis
import pymc as pm

# from anopheles.species.darlingi import *
from anopheles.species.gambiae import *
# from anopheles.species.arabiensis import *
# from anopheles.species.stephensi import *

s = Session()
species = dict([sp[::-1] for sp in anopheles.list_species(s)])
species_tup = (species[species_name], species_name)

from mpl_toolkits import basemap
import pylab as pl

pl.close('all')

mask, x, img_extent = anopheles.make_covering_raster(100, env)
mask, x, img_extent = anopheles.make_covering_raster(20, env)
# outside_lat = (x[:,1]*180./np.pi>38)+(x[:,1]*180./np.pi<-36)
# outside_lon = (x[:,0]*180./np.pi>56)+(x[:,0]*180./np.pi<-18)
mask, x, img_extent = anopheles.subset_x(mask,x,img_extent,(-18,-36,56,38))

spatial_submodel = anopheles.lr_spatial_env
# spatial_submodel = anopheles.nogp_spatial_env
# n_in = n_out = 2

# spatial_submodel = lr_spatial_env
n_in = 400
n_out = 1000

# spatial_submodel = spatial_env
# n_out = 400
# n_in = 100

M = anopheles.species_MCMC(s, species_tup, spatial_submodel, with_eo = True, with_data = True, env_variables = env, constraint_fns=cf,n_in=n_in,n_out=n_out)
# M = anopheles.restore_species_MCMC(s, 'Anopheles gambiae s.s.2009-10-26 11:57:46.766486.hdf5')
# from time import time
# t1 = time()
M.isample(50000,0,10)
# print time()-t1
# xtest = np.array([[.1,.1],[.05,.05],[0,0]])
# atest = np.array([1,0,1])
# v= anopheles.plot_validation(M,s,xtest,atest)

# M.assign_step_methods()
# sf=M.step_method_dict[M.f_fr][0]    
# ss=M.step_method_dict[M.p_find][0]
# sa = M.step_method_dict[M.ctr][0]

# M.assign_step_methods()
# M.isample(50000,0,10,verbose=0)
# pm.Matplot.plot(M)
# for name in ['ctr','val','coefs','const']:
#     pl.figure()
#     pl.plot(M.trace(name)[:])
#     pl.title(name)
# 
# # mask, x, img_extent = make_covering_raster(2)
# # b = basemap.Basemap(*img_extent)
# # out = M.p.value(x)
# # arr = np.ma.masked_array(out, mask=True-mask)
# # b.imshow(arr.T, interpolation='nearest')
# # pl.colorbar()
# pl.figure()
# anopheles.current_state_map(M, s, species[species_num], mask, x, img_extent, thin=100)
# pl.title('Final')
# pl.savefig('final.pdf')
# pl.figure()
# pl.plot(M.trace('out_prob')[:],'b-',label='out')
# pl.plot(M.trace('in_prob')[:],'r-',label='in')    
# pl.legend(loc=0)
# 
# pl.figure()
# out, arr = anopheles.presence_map(M, s, species_tup, thin=100, burn=250, trace_thin=10)
# pl.figure()
# x_disp, samps = mean_response_samples(M, -1, 10, burn=100, thin=1)
# for s in samps:
#     pl.plot(x_disp, s)
# pl.savefig('prob_%s.pdf'%species_name)
# 
# pl.figure()
# p_atfound = probability_traces(M)
# p_atnotfound = probability_traces(M,False)
# pl.savefig('presence.pdf')
