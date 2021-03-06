# from autodiff import Function, Gradient
import numpy as np

from .. import Solution
from ..Algorithm import Algorithm
from .SingleShooting import SingleShooting
from math import *
from beluga.utils import *
from beluga.utils import Propagator
from beluga.utils.Worker import Worker
import logging, sys, os


try:
    from mpi4py import MPI
    HPCSUPPORTED = 1
except ImportError:
    HPCSUPPORTED = 0

class MultipleShooting(Algorithm):
    def __new__(cls, tolerance=1e-6, max_iterations=100, max_error=100, derivative_method='fd', cache_dir = None,verbose=False,cached=True,number_arcs=-1):
        obj = super(MultipleShooting, cls).__new__(cls)
        if number_arcs == 1:
            return SingleShooting(tolerance=tolerance, max_iterations=max_iterations, max_error=max_error, derivative_method=derivative_method, cache_dir=cache_dir, verbose=verbose, cached=cached)
        return obj

    def __init__(self, tolerance=1e-6, max_iterations=100, max_error=100, derivative_method='fd', cache_dir = None,verbose=False,cached=True,number_arcs=-1):
        self.tolerance = tolerance
        self.max_iterations = max_iterations
        self.verbose = verbose
        self.max_error = max_error
        self.derivative_method = derivative_method
        if derivative_method == 'csd':
            self.stm_ode_func = self.__stmode_csd
            self.bc_jac_func  = self.__bcjac_fd
        elif derivative_method == 'fd':
            self.stm_ode_func = self.__stmode_fd
            self.bc_jac_func  = self.__bcjac_fd
        else:
            raise ValueError("Invalid derivative method specified. Valid options are 'csd' and 'fd'.")
        self.cached = cached
        if cached and cache_dir is not None:
            self.set_cache_dir(cache_dir)
        self.number_arcs = number_arcs

        # TODO: Implement the host worker in a nicer way
        # Start Host MPI process
        # self.worker = Worker(mode='HOST')
        # self.worker.startWorker()
        # self.worker.Propagator.setSolver(solver='ode45')
        self.worker = None

    def set_cache_dir(self,cache_dir):
        self.cache_dir = cache_dir
        if self.cached and cache_dir is not None:
            raise NotImplementedError
            # TODO: Fix this cache function. It used an old outdated package that no longer works.
            # memory = Memory(cachedir=cache_dir, mmap_mode='r', verbose=0)
            self.solve = memory.cache(self.solve)

    def __bcjac_csd(self, bc_func, ya, yb, phi, parameters, aux, StepSize=1e-50):
        ya = np.array(ya, dtype=complex)
        yb = np.array(yb, dtype=complex)
        # if parameters is not None:
        p  = np.array(parameters, dtype=complex)
        h = StepSize

        nOdes = ya[0].shape[0]
        nBCs = nOdes + nOdes*(self.number_arcs - 1)
        if parameters is not None:
            nBCs += parameters.size

        fx = bc_func(ya,yb,parameters,aux)

        M = [np.zeros((nBCs, nOdes)) for _ in range(self.number_arcs)]
        N = [np.zeros((nBCs, nOdes)) for _ in range(self.number_arcs)]
        J = [None for _ in range(self.number_arcs)]
        for arc in range(self.number_arcs):
            for i in range(nOdes):
                ya[arc][i] += h*1j
                f = bc_func(ya,yb,p,aux)
                M[arc][:,i] = np.imag(f)/h
                ya[arc][i] -= h*1j

                yb[arc][i] += h*1j
                f = bc_func(ya,yb,p,aux)
                N[arc][:,i] = np.imag(f)/h
                yb[arc][i] -= h*1j
            J[arc] = M[arc]+np.dot(N[arc],phi[arc])

        if parameters is not None:
            P = np.zeros((nBCs, p.size))
            for i in range(p.size):
                p[i] = p[i] + h*1j
                f = bc_func(ya,yb,p,aux)
                P[:,i] = np.imag(f)/h
                p[i] = p[i] - h*1j
            J.append(P)

        J = np.hstack(J)
        return J

    def __bcjac_fd(self, bc_func, ya, yb, phi, parameters, aux, StepSize=1e-6):
        # if parameters is not None:
        p  = np.array(parameters)
        h = StepSize

        nOdes = ya[0].shape[0]
        nBCs = nOdes + nOdes*(self.number_arcs - 1)
        if parameters is not None:
            nBCs += parameters.size

        fx = bc_func(ya,yb,parameters,aux)

        M = [np.zeros((nBCs, nOdes)) for _ in range(self.number_arcs)]
        N = [np.zeros((nBCs, nOdes)) for _ in range(self.number_arcs)]
        J = [None for _ in range(self.number_arcs)]
        for arc in range(self.number_arcs):
            for i in range(nOdes):
                ya[arc][i] += h
                f = bc_func(ya,yb,p,aux)
                M[arc][:,i] = (f-fx)/h
                ya[arc][i] -= h

                yb[arc][i] += h
                f = bc_func(ya,yb,p,aux)
                N[arc][:,i] = (f-fx)/h
                yb[arc][i] -= h
            J[arc] = M[arc]+np.dot(N[arc],phi[arc])

        if parameters is not None:
            P = np.zeros((nBCs, p.size))
            for i in range(p.size):
                p[i] = p[i] + h
                f = bc_func(ya,yb,p,aux)
                P[:,i] = (f-fx)/h
                p[i] = p[i] - h
            J.append(P)

        J = np.hstack(J)
        return J

    def __stmode_fd(self, x, y, odefn, parameters, aux, nOdes = 0, StepSize=1e-6):
        "Finite difference version of state transition matrix"
        N = y.shape[0]
        nOdes = int(0.5*(sqrt(4*N+1)-1))

        phi = y[nOdes:].reshape((nOdes, nOdes)) # Convert STM terms to matrix form
        Y = np.array(y[0:nOdes])  # Just states
        F = np.zeros((nOdes, nOdes))

        # Compute Jacobian matrix, F using finite difference
        fx = (odefn(x, Y, parameters, aux)).real
        for i in range(nOdes):
            Y[i] += StepSize
            F[:, i] = (odefn(x, Y, parameters, aux) - fx).real/StepSize
            Y[i] -= StepSize

        phiDot = np.dot(F, phi)
        return np.concatenate((fx, np.reshape(phiDot, (nOdes*nOdes))))

    def __stmode_csd(self, x, y, odefn, parameters, aux, StepSize=1e-100):
        "Complex step version of State Transition Matrix"
        N = y.shape[0]
        nOdes = int(0.5 * (sqrt(4 * N + 1) - 1))

        phi = y[nOdes:].reshape((nOdes, nOdes))  # Convert STM terms to matrix form
        Y = np.array(y[0:nOdes], dtype=complex)  # Just states
        F = np.zeros((nOdes, nOdes))

        # Compute Jacobian matrix, F using finite difference
        for i in range(nOdes):
            Y[i] += StepSize * 1.j
            F[:, i] = np.imag(odefn(x, Y, parameters, aux)) / StepSize
            Y[i] -= StepSize * 1.j

        # Phidot = F*Phi (matrix product)
        phiDot = np.dot(F, phi)
        return np.concatenate((odefn(x, y, parameters, aux), np.reshape(phiDot, (nOdes * nOdes))))

    # def __stmode_ad(self, x, y, odefn, parameters, aux, nOdes = 0, StepSize=1e-50):
    #     "Automatic differentiation version of State Transition Matrix"
    #     phi = y[nOdes:].reshape((nOdes, nOdes)) # Convert STM terms to matrix form
    #     # Y = np.array(y[0:nOdes],dtype=complex)  # Just states
    #     # F = np.zeros((nOdes,nOdes))
    #     # # Compute Jacobian matrix using complex step derivative
    #     # for i in range(nOdes):
    #     #     Y[i] = Y[i] + StepSize*1.j
    #     #     F[:,i] = np.imag(odefn(x, Y, parameters, aux))/StepSize
    #     #     Y[i] = Y[i] - StepSize*1.j
    #     f = Function(odefn)
    #     g = Gradient(odefn)
    #
    #     # Phidot = F*Phi (matrix product)
    #     # phiDot = np.real(np.dot(F,phi))
    #     phiDot = np.real(np.dot(g(x,y,paameters,aux),phi))
    #     # return np.concatenate( (odefn(x,y, parameters, aux), np.reshape(phiDot, (nOdes*nOdes) )) )
    #     return np.concatenate( f(x,y,parameters,aux), np.reshape(phiDot, (nOdes*nOdes) ))


    # @staticmethod
    # def ode_wrap(func,*args, **argd):
    #    def func_wrapper(x,y0):
    #        return func(x,y0,*args,**argd)
    #    return func_wrapper

    def get_bc(self,ya,yb,p,aux):
        f1 = self.bc_func(ya[0],yb[-1],p,aux)
        for i in range(self.number_arcs-1):
            nextbc = yb[i]-ya[i+1]
            f1 = np.concatenate((f1,nextbc)).astype(np.float64)
        return f1

    def solve(self,bvp):
        """Solve a two-point boundary value problem
            using the multiple shooting method

        Args:
            deriv_func: the ODE function
            bc_func: the boundary conditions function
            solinit: a "Solution" object containing the initial guess
        Returns:
            solution of TPBVP
        Raises:
        """
        guess = bvp.solution

        if self.worker is not None:
            ode45 = self.worker.Propagator
        else:
            # Start local pool
            ode45 = Propagator(solver='ode45',process_count=self.number_arcs)
            ode45.startPool()

        # Decrease time step if the number of arcs is greater than the number of indices
        if self.number_arcs >= len(guess.x):
            x,ynew = ode45(bvp.deriv_func, np.linspace(guess.x[0],guess.x[-1],self.number_arcs+1), guess.y[:,0], guess.parameters, guess.aux, abstol=self.tolerance/10, reltol=1e-3)
            guess.y = np.transpose(ynew)
            guess.x = x

        solinit = guess
        x = solinit.x
        # Get initial states from the guess structure
        y0g = [solinit.y[:,int(np.floor(i/self.number_arcs*x.shape[0]))] for i in range(self.number_arcs)]
        paramGuess = solinit.parameters

        deriv_func = bvp.deriv_func
        self.bc_func = bvp.bc_func
        aux = bvp.solution.aux
        # Only the start and end times are required for ode45
        t0 = x[0]
        tf = x[-1]
        t = x

        # Extract number of ODEs in the system to be solved
        nOdes = solinit.y.shape[0]

        # Initial state of STM is an identity matrix
        stm0 = np.eye(nOdes).reshape(nOdes*nOdes)

        if solinit.parameters is None:
            nParams = 0
        else:
            nParams = solinit.parameters.size

        iter = 1            # Initialize iteration counter
        converged = False   # Convergence flag

        # Ref: Solving Nonlinear Equations with Newton's Method By C. T. Kelley
        # Global Convergence and Armijo's Rule, pg. 11
        alpha = 1
        beta = 1
        r0 = None
        phiset = [np.eye(nOdes) for i in range(self.number_arcs)]
        tspanset = [np.empty(t.shape[0]) for i in range(self.number_arcs)]

        tspan = [t0,tf]

        try:
            while True:
                if iter>self.max_iterations:
                    logging.warn("Maximum iterations exceeded!")
                    break

                y0set = [np.concatenate( (y0g[i], stm0) ) for i in range(self.number_arcs)]

                for i in range(self.number_arcs):
                    left = int(np.floor(i/self.number_arcs*t.shape[0]))
                    right = int(np.floor((i+1)/self.number_arcs*t.shape[0]))
                    if i == self.number_arcs-1:
                        right = t.shape[0] - 1
                    tspanset[i] = [t[left],t[right]]
                    #tspanset[i] = np.linspace(t[left],t[right],np.ceil(5000/self.number_arcs))

                # Propagate STM and original system together
                tset,yySTM = ode45(self.stm_ode_func, tspanset, y0set, deriv_func, paramGuess, aux, abstol=self.tolerance/10, reltol=1e-5)

                # Obtain just last timestep for use with correction
                yf = [yySTM[i][-1] for i in range(self.number_arcs)]
                # Extract states and STM from ode45 output
                yb = [yf[i][:nOdes] for i in range(self.number_arcs)]  # States
                phiset = [np.reshape(yf[i][nOdes:],(nOdes, nOdes)) for i in range(self.number_arcs)] # STM

                # y1 = yySTM[0][:, :nOdes]
                # for i in range(1, self.number_arcs):
                #     y1 = np.vstack((y1, (yySTM[i][1:, :nOdes])))
                #
                # for i in range(0,len(y1[:,3])):
                #     print('den = ' + str((-0.5 * 1 * y1[i,3] * cos(y1[i,7]) - 1 * y1[i,5] * sin(y1[i,7]))) + '  u =' + str(y1[i,7]) + '  lamX =' + str(y1[i,3]) + '  lamA =' + str(y1[i,5]))

                # Evaluate the boundary conditions
                res = self.get_bc(y0g, yb, paramGuess, aux)

                # Compute correction vector
                r1 = np.linalg.norm(res)
                if r1 > self.max_error:
                    logging.warn('Residue: '+str(r1) )
                    logging.warn('Residue exceeded max_error')
                    raise RuntimeError('Residue exceeded max_error')

                if self.verbose:
                    logging.debug('Residue: '+str(r1))

                # Solution converged if BCs are satisfied to tolerance
                if max(abs(res)) < self.tolerance:
                    if self.verbose:
                        logging.info("Converged in "+str(iter)+" iterations.")
                    converged = True
                    break
                # logging.debug(paramGuess)
                # Compute Jacobian of boundary conditions using numerical derviatives
                J   = self.bc_jac_func(self.get_bc, y0g, yb, phiset, paramGuess, aux).astype(np.float64)
                # if r0 is not None:
                #     beta = (r0-r1)/(alpha*r0)
                #     if beta < 0:
                #         beta = 1
                # if r1>1:
                #     alpha = 1/(2*r1)
                # else:
                #     alpha = 1
                alpha = 0.5
                beta = 1.0

                r0 = r1

                # No damping if error within one order of magnitude
                # of tolerance
                if r1 < 10*self.tolerance:
                    alpha, beta = 1, 1

                dy0 = alpha*beta*np.linalg.solve(J,-res)

                #dy0 = -alpha*beta*np.dot(np.transpose(np.dot(np.linalg.inv(np.dot(J,np.transpose(J))),J)),res)

                # dy0 = np.linalg.solve(J,-res)
                # if abs(r1 - 0.110277711594) < 1e-4:
                #     from beluga.utils import keyboard

                # Apply corrections to states and parameters (if any)

                if nParams > 0:
                    dp = dy0[(nOdes*self.number_arcs):]
                    dy0 = dy0[:(nOdes*self.number_arcs)]
                    paramGuess = paramGuess + dp
                    for i in range(self.number_arcs):
                        y0g[i] = y0g[i] + dy0[(i*nOdes):((i+1)*nOdes)]
                else:
                    y0g = y0g + dy0
                iter = iter+1
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            logging.warn(fname+'('+str(exc_tb.tb_lineno)+'): '+str(exc_type))

        # Now program stitches together solution from the multiple arcs instead of propagating from beginning.
        # This is important for sensitive problems because they can diverge from the actual solution if propagated in single arc.
        # Therefore, the initial guess for next step and data for plotting are much better.
        if converged:
            # x1, y1 = ode45.solve(deriv_func, [x[0],x[-1]], y0g[0], paramGuess, aux, abstol=1e-6, reltol=1e-6)
            # sol = Solution(x1,y1.T,paramGuess)
            x1 = tset[0]
            y1 = yySTM[0][:, :nOdes]
            for i in range(1, self.number_arcs):
                x1 = np.hstack((x1, tset[i][1:]))
                y1 = np.vstack((y1, (yySTM[i][1:, :nOdes])))
            sol = Solution(x1, y1.T, paramGuess)
        else:
            # Return initial guess if it failed to converge
            sol = solinit

        sol.converged = converged
        bvp.solution = sol
        sol.aux = aux

        if self.worker is None:
            ode45.closePool()
        return sol
