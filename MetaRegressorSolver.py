from Polysolver import PolynomialSolver, PolyGASolver
import numpy as np
from copy import deepcopy
import matplotlib.pyplot as plt
from selection_functions import minmax
from copy import deepcopy
import pdb

'''
Meta solver for polynomial regression with unknown objective
'''

class MetaRegressor(object):
    

    def __init__(self, loss_fun, pop_size=20, min_pop=5,mutation_rate=0.2,
                crossover_point_rate = 0.5, seed=None, noise=[0.5,1,0.1,0.01], ga=True, solver_params={}, max_deg=10):
        self.pop_size = pop_size
        self.min_pop = min_pop
        self.mutation_rate = mutation_rate
        self.crossover_point_rate = crossover_point_rate
        self.noise = noise
        self.ga = ga
        self.solver_params = solver_params

        self.loss_fun = loss_fun
        self.max_deg = max_deg

        self.rg = np.random.RandomState(seed)
        self.reset()


    #Get new solver with given hyperparameters
    def get_new_individual(self,params=None):
        if params is None:
            l2 = np.exp(self.rg.rand()*3)
            degree = self.rg.randint(self.max_deg)+1
            l1 = self.rg.rand()*0.1
            gamma = self.rg.rand()
        else:
            l2, degree, gamma, l1 = params
        
        if self.ga:
            model = PolyGASolver(l1=l1,l2=l2, degree=degree, gamma=gamma, **self.solver_params)
        else:
            model = PolynomialSolver(l1=l1,l2=l2, degree=degree, gamma=gamma, **self.solver_params)
        model.initialize()
        return [model, l2, degree, gamma, l1]
    
    def reset(self):
        self.current_pop_ = [self.get_new_individual() for i in range(self.pop_size)]
        self.current_pop = [x[1:] for x in self.current_pop_]
        self.solvers = [x[0] for x in self.current_pop_]
        
    #Evaluate the prediction error
    def evalpop(self, x,y):
        assert len(x) == len(y), "Improper input eval"
        self.costs = np.zeros(self.gen_size)
        for i in range(self.gen_size):
            #Use blackbox loss function to evaluate error
            self.costs[i] = self.loss_fun(self.solvers[i].predict(x,best=True),y,x)
    
    @property
    def gen_size(self):
        return len(self.current_pop)
    
    #Perturb the hyperparameters
    def mutate(self, ind_):
        ind = deepcopy(ind_)
        for i in range(4):
            if i == 1:
                ind[i] += self.rg.choice([1,-1])
                if ind[i]<0:
                    ind[i] = self.max_deg
            else:
                ind[i] = max(0,self.rg.randn()+self.noise[i])
        return self.get_new_individual(params=ind)
    
    #Swap two individuals' hyperparameters
    def crossover(self, ind1_, ind2_):
        ind1, ind2 = deepcopy(ind1_), deepcopy(ind2_)
        t = False
        for i in range(4):
            if self.rg.rand() < self.crossover_point_rate:
                ind1[i], ind2[i] = ind2[i], ind1[i]
                t = True
        
        return ind1, ind2, t

    def init_solver(self,crossover_rate = 0.1,fitness=None,
                selection_fun = None,cut_frac=1.0,percentile=50):
    
        self.fitness = fitness
        self.cut_frac = cut_frac
        self.percentile = percentile
        self.crossover_rate = crossover_rate

        if self.fitness is None:
            self.fitness = lambda cost: -cost

        self.selection_fun = selection_fun
        if self.selection_fun is None:
            self.selection_fun = minmax
        
        self.max_pop=self.pop_size
        self.bestperf = []
    
    #TRAIN lower level regrssion solvers
    def one_step_train(self, x,y,epochs=100, debug=False):
        for ind in self.solvers:
            ind.fit(x,y,epochs=epochs, debug=debug)
    
    #Selection
    def evolve(self, x, y):
        self.evalpop(x, y)

        #Get fitness
        fitness = self.fitness(self.costs)
        bestsoln = np.argmax(fitness)

        #Selection strategy
        select_index = self.selection_fun(fitness=fitness,gen_size=self.gen_size, cut_frac=self.cut_frac, percentile=self.percentile)
        if not (bestsoln in select_index):
            select_index = np.append(select_index,bestsoln)
        
        self.current_pop = [self.current_pop[i] for i in select_index]
        self.solvers = [self.solvers[i] for i in select_index]

        self.evalpop(x, y)
        fitness = self.fitness(self.costs)
        bestsoln = np.argmax(fitness)

        new_pop = deepcopy(self.current_pop)

        #Do crossovers with remaining polulation
        for i in range(self.gen_size):
            ind = self.current_pop[i]
            ind2_idx = self.rg.randint(self.gen_size)
            ind2 = self.current_pop[ind2_idx]

            if self.rg.rand() < self.crossover_rate:
                
                new_ind1, new_ind2, t = self.crossover(ind,ind2)
                if t:
                    s1, s2 = self.get_new_individual(new_ind1)[0], self.get_new_individual(new_ind2)[0]
                    if self.max_pop is None or self.gen_size<self.max_pop:
                        new_pop.append(new_ind1)
                        self.solvers.append(s1)
                        new_pop.append(new_ind2)
                        self.solvers.append(s2)
                    elif i != bestsoln:
                        #self.solvers[i].close()
                        #self.solvers[ind2_idx].close()
                        new_pop[i] = new_ind1
                        self.solvers[i] = s1
                        new_pop[ind2_idx] = new_ind2
                        self.solvers[ind2_idx] = s2
                
            if i != bestsoln and self.rg.rand() < self.mutation_rate:
                new_ind = self.mutate(ind)
                new_pop[i] = new_ind[1:]
                #self.solvers[i].close()
                self.solvers[i] = new_ind[0]
        
        self.current_pop = new_pop
        
        # Maintain above min population size
        while self.gen_size <= self.min_pop:
            ind = self.current_pop[bestsoln]
            ind2_idx = self.rg.randint(self.gen_size)
            ind2 = self.current_pop[ind2_idx]

            if self.rg.rand() < self.crossover_rate:
                
                new_ind1, new_ind2, t = self.crossover(ind,ind2)
                if t:
                    s1, s2 = self.get_new_individual(new_ind1)[0], self.get_new_individual(new_ind2)[0]
                    
                    self.current_pop.append(new_ind1)
                    self.solvers.append(s1)
                    self.current_pop.append(new_ind2)
                    self.solvers.append(s2)
            
            new_ind = self.mutate(ind)
            self.current_pop.append(new_ind[1:])
            #self.solvers[i].close()
            self.solvers.append(new_ind[0])
                
        self.evalpop(x, y)
    
    #Training procedure
    def train(self,xtrain,ytrain,xtest, ytest,iters, subiters=100, debug_2=False, plot=True, plot_curve = False):
        #self.evalpop(xtest, ytest)
        #self.bestidx = np.argmin(self.costs)
        #self.bestperf.append(self.costs[self.bestidx])
        for i in range(iters):
            #Train lower level solvers
            self.one_step_train(xtrain,ytrain,subiters, debug_2)
            #evolve objective functions
            self.evolve(xtest,ytest)
            self.bestidx = np.argmin(self.costs)
            self.bestperf.append(self.costs[self.bestidx])
            print("Gen:",(i+1),"Cost:",self.bestperf[-1])
            print("Params:",self.current_pop[self.bestidx])
            if plot_curve:
                y = self.predict(xtrain)
                idx = np.argsort(xtrain)
                plt.clf()
                plt.plot(xtrain[idx], y[idx],label='Predict')
                plt.plot(xtrain[idx], ytrain[idx],label='Actual')
                plt.legend()
                plt.pause(0.1)
        
        if plot:
            plt.clf()
            plt.xlabel('Generations')
            plt.ylabel('Error')
            plt.plot(np.arange(len(self.bestperf))+1, self.bestperf)
    
    #Prediction based on best solver's solution
    def predict(self, xtest):
        self.bestidx = np.argmin(self.costs)
        return self.solvers[self.bestidx].predict(xtest, best=True)

