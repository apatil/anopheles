import numpy as np
import cov_prior
from mahalanobis_covariance import *
import pymc as pm

__all__ = ['spatial_hill','hill_fn','hinge','step','lr_spatial','lr_spatial_env','MVNLRParentMetropolis','minimal_jumps','bookend']

def hinge(x, cp):
    "A MaxEnt hinge feature"
    y = x-cp
    y[x<cp]=0.
    return y
    
def step(x,cp):
    "A MaxEnt step feature"
    y = np.ones(x.shape)
    y[x<cp]=0.
    return y


# =============================
# = The standard spatial hill =
# =============================
class hill_fn(object):
    "Closure used by spatial_hill"    
    def __init__(self, val, vec, ctr, amp):
        self.val = val
        self.vec = vec
        self.ctr = ctr
        self.amp = amp
        self.max_argsize = np.inf
        
    def __call__(self, x):
        xr = x.reshape(-1,2)
        dev = xr-self.ctr
        tdev = np.dot(dev, self.vec)
        if len(dev.shape)==1:
            ax=0
        else:
            ax=-1
        return pm.invlogit(np.sum(tdev**2/self.val,axis=ax)*self.amp).reshape(x.shape[:-1])


def spatial_hill(**kerap):
    "For debugging only"
    amp = pm.Uninformative('amp',-1)
    
    @pm.stochastic
    def ctr(value=np.array([0,0])):
        "This makes the center uniformly distributed over the surface of the earth."
        if value[0] < -np.pi or value[0] > np.pi or value[1] < -np.pi/2. or value[1] > np.pi/2.:
            return -np.inf
        return np.cos(value[1])

    bump_eigenvalues = pm.Gamma('bump_eigenvalues', 2, 2, size=2)
    bump_eigenvectors = cov_prior.OrthogonalBasis('bump_eigenvectors',2)
    
    @pm.deterministic
    def p(val = bump_eigenvalues, vec = bump_eigenvectors, ctr = ctr, amp=amp):
        "A stupid hill, using Euclidean distance."
        return hill_fn(val, vec, ctr, amp)
        
    return locals()


# =======================================
# = The spatial-only, low-rank submodel =
# =======================================
def mod_matern(x,y,diff_degree,amp,scale,symm=False):
    """Matern with the mean integrated out."""
    return pm.gp.matern.geo_rad(x,y,diff_degree=diff_degree,amp=amp,scale=scale,symm=symm)+10000

def bookend(A, Ufro, Ubak):
    return np.dot(pm.gp.trisolve(Ufro[:,:Ufro.shape[0]], A.T, uplo='U', transa='N'), Ubak[:,:Ubak.shape[0]]).T

def minimal_jumps(piv_old, U_old, piv_new, U_new):
    """
    Returns the matrices giving the minimal-squared-error forward and backward jumps
    when piv_new and U_new are proposed as replacements for piv_old and U_old.
    
    Converts first to the independent unit normals underlying the current and
    proposed states.
    """
    U_old_sorted = U_old[:,np.argsort(piv_old)]
    U_new_sorted = U_new[:,np.argsort(piv_new)]
    
    oldnew = np.dot(U_old_sorted, U_new_sorted.T)
    oldold = np.dot(U_old_sorted, U_old_sorted.T)
    newnew = np.dot(U_new_sorted, U_new_sorted.T)
    
    forjump = np.linalg.solve(newnew, oldnew.T)
    bakjump = np.linalg.inv(np.linalg.solve(oldold, oldnew))
    
    return bookend(forjump, U_old, U_new), bookend(bakjump, U_old, U_new)
        
class MVNLRParentMetropolis(pm.AdaptiveMetropolis):
    def __init__(self, variables, mvn, U, piv, rl, cov=None, delay=1000, scales=None, interval=200, greedy=True, shrink_if_necessary=False, verbose=0, tally=False):
        pm.AdaptiveMetropolis.__init__(self, variables, cov, delay, scales, interval, greedy, shrink_if_necessary,verbose, tally)
        self.mvn = mvn
        self.piv = piv
        self.U = U
        self.rl = rl
        
    def propose(self):
        piv_old = self.piv.value
        U_old = self.U.value
        
        pm.AdaptiveMetropolis.propose(self)
        try:
            self.logp_plus_loglike
        except pm.ZeroProbability:
            self.reject()
        forjump, bakjump = minimal_jumps(piv_old, U_old, self.piv.value, self.U.value)
        
        # Symmetric proposal
        if np.random.randint(2)==0:
            jump = forjump
        else:
            jump = bakjump
        
        self.mvn.value = np.dot(jump, self.mvn.value)
        
    def reject(self):
        pm.AdaptiveMetropolis.reject(self)
        self.mvn.revert()
        
        
class LRP(object):
    """A closure that can evaluate a low-rank field."""
    def __init__(self, x_fr, C, krige_wt):
        self.x_fr = x_fr
        self.C = C
        self.krige_wt = krige_wt
    def __call__(self, x):
        f_out = np.dot(np.asarray(self.C(x,self.x_fr)), self.krige_wt)
        # return pm.invlogit(f_out).reshape(x.shape[:-1])
        return (f_out > 0).reshape(x.shape[:-1]).astype('int')
        
def lr_spatial(rl=50,**stuff):
    """A low-rank spatial-only model."""
    amp = pm.Exponential('amp',.1,value=1)
    scale = pm.Exponential('scale',.1,value=1.)
    diff_degree = pm.Uniform('diff_degree',0,2,value=.5)

    pts_in = stuff['pts_in']
    pts_out = stuff['pts_out']
    x_eo = np.vstack((pts_in, pts_out))

    @pm.deterministic
    def C(amp=amp,scale=scale,diff_degree=diff_degree):
        return pm.gp.Covariance(mod_matern, amp=amp, scale=scale, diff_degree=diff_degree)

    @pm.deterministic(trace=False)
    def ichol(C=C, rl=rl, x=x_eo):
        return C.cholesky(x, rank_limit=rl, apply_pivot=False)

    piv = pm.Lambda('piv', lambda d=ichol: d['pivots'])
    U = pm.Lambda('U', lambda d=ichol: d['U'].view(np.ndarray), trace=False)

    # Trace the full-rank locations
    x_fr = pm.Lambda('x_fr', lambda d=ichol, rl=rl, x=x_eo: x[d['pivots'][:rl]])

    # Evaluation of field at expert-opinion points
    U_fr = U[:rl,:rl]
    L_fr = pm.Lambda('L_fr', lambda U=U_fr: U.T)
    f_fr = pm.MvNormalChol('f_fr', np.zeros(rl), L_fr)   

    @pm.deterministic(trace=False)
    def krige_wt(f_fr = f_fr, U_fr = U_fr):
        return pm.gp.trisolve(U_fr,pm.gp.trisolve(U_fr,f_fr,uplo='U',transa='T'),uplo='U',transa='N',inplace=True)

    p = pm.Lambda('p', lambda x_fr=x_fr, C=C, krige_wt=krige_wt: LRP(x_fr, C, krige_wt))

    return locals()            
    
# ======================================
# = Spatial and environmental low-rank =
# ======================================
def mod_spatial_mahalanobis(x,y,val,vec,const_frac,symm=False):
    cf = np.asscalar(const_frac)
    return spatial_mahalanobis_covariance(x,y,1,val,vec,symm)*(1.-cf) + cf

def normalize_env(x, means, stds):
    x_norm = x.copy().reshape(-1,x.shape[-1])
    for i in xrange(2,x_norm.shape[1]):
        x_norm[:,i] -= means[i-2]
        x_norm[:,i] /= stds[i-2]
    return x_norm

class LRP_norm(LRP):
    """
    A closure that can evaluate a low-rank field.
    
    Normalizes the third argument onward.
    """
    def __init__(self, x_fr, C, krige_wt, means, stds):
        LRP.__init__(self, x_fr, C, krige_wt)
        self.means = means
        self.stds = stds

    def __call__(self, x):
        x_norm = normalize_env(x, self.means, self.stds)
        return LRP.__call__(self, x_norm.reshape(x.shape))

def lr_spatial_env(rl=50,**stuff):
    """A low-rank spatial-only model."""
    # amp = pm.Exponential('amp',.1,value=10)
    const_frac = pm.Uniform('const_frac',0,1,value=.1)

    pts_in = np.hstack((stuff['pts_in'],stuff['env_in']))
    pts_out = np.hstack((stuff['pts_out'],stuff['env_out']))
    x_eo = normalize_env(np.vstack((pts_in, pts_out)), stuff['env_means'], stuff['env_stds'])
    
    n_env = stuff['env_in'].shape[1]
    
    val = pm.Gamma('val',4,4,value=np.ones(n_env+1))
    vec = cov_prior.OrthogonalBasis('vec',n_env+1,constrain=False)

    @pm.deterministic
    def C(val=val,vec=vec,const_frac=const_frac):
        return pm.gp.Covariance(mod_spatial_mahalanobis, val=val, vec=vec, const_frac=const_frac)

    @pm.deterministic(trace=False)
    def ichol(C=C, rl=rl, x=x_eo):
        return C.cholesky(x, rank_limit=rl, apply_pivot=False)
                
    @pm.potential
    def rank_check(d=ichol):
        if d['U'].shape[0]<rl:
            return -np.inf
        else:
            return 0.
    

    piv = pm.Lambda('piv', lambda d=ichol: d['pivots'])
    U = pm.Lambda('U', lambda d=ichol: d['U'].view(np.ndarray), trace=False)
    
    U_fr = pm.Lambda('U_fr', lambda U=U, rl=rl: U[:,:rl], trace=False)
    L_fr = pm.Lambda('L_fr', lambda U=U_fr: U.T, trace=False)

    # Trace the full-rank locations
    x_fr = pm.Lambda('x_fr', lambda d=ichol, rl=rl, x=x_eo: x[d['pivots'][:rl]])

    # Evaluation of field at expert-opinion points
    f_fr = pm.MvNormalChol('f_fr', np.zeros(rl), L_fr)

    @pm.deterministic(trace=False)
    def krige_wt(f_fr=f_fr, U_fr=U_fr):
        return pm.gp.trisolve(U_fr,pm.gp.trisolve(U_fr,f_fr,uplo='U',transa='T'),uplo='U',transa='N',inplace=True)

    p = pm.Lambda('p', lambda x_fr=x_fr, C=C, krige_wt=krige_wt, means=stuff['env_means'], stds=stuff['env_stds']: LRP_norm(x_fr, C, krige_wt, means, stds))

    return locals()