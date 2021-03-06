import dill
import numpy as np
import numexpr as ne
import collections
from sympy import *
from sympy.utilities.lambdify import lambdify

class Plot(object):
    """
    Represents a single plot with axes, labels, expressions to evaluate etc.
    """
    def __init__(self, step, sol, mesh_size):
        self.step_index = step
        self.sol_index = sol
        self.mesh_size = mesh_size
        self.plot_data = []
        self._title = self._xlabel = self._ylabel = self._xlim = self._ylim = None
        self._grid_on = True

    def xlabel(self, label):
        self._xlabel = label
        return self

    def ylabel(self, label):
        self._ylabel = label
        return self

    def step(self, _step):
        self.step_index = _step
        return self

    def solution(self, _sol):
        self.sol_index = _sol
        return self

    def grid_on(self, _grid_on):
        self._grid_on = _grid_on
        return self

    def xlim(self, _xlim):
        self._xlim = _xlim
        return self

    def ylim(self, _ylim):
        self._ylim = _ylim
        return self

    def title(self, title_txt):
        """
        Sets the title of the figure
        """
        self._title = title_txt
        return self

    def line(self, x_expr, y_expr, color = None, legend = None, step = None, sol = None):
        """
        Adds a new line plot to the figure
        """
        # TODO: Datatype sanity checks needed here
        self.plot_data.append({'type':'line', 'x':x_expr, 'y':y_expr, 'color':color, 'legend':legend, 'step':step, 'sol':sol})
        return self

    def line_series(self, x_expr, y_expr, color = None, legend = None, step = None, start = 0, skip = 0, end = -1):
        self.plot_data.append({'type':'line_series', 'x':x_expr, 'y':y_expr, 'color':color, 'legend':legend, 'step':step, 'start':start, 'skip':skip, 'end': end})
        return self

    def preprocess(self, solution, problem_data):
        """
        Evaluates the expressions using the supplied data
        """
        for line in self.plot_data:
            step_idx = line['step'] if line['step'] is not None else self.step_index
            line['data'] = []
            if line['type'] == 'line':
                sol_idx = line['sol'] if line['sol'] is not None else self.sol_index
                sol = solution[step_idx][sol_idx]

                sol.prepare(problem_data, mesh_size=self.mesh_size, overwrite=False)
                line['data'].append({'x_data': sol.evaluate(line['x']),
                                     'y_data': sol.evaluate(line['y'])})
            elif line['type'] == 'line_series':
                sol_set = solution[step_idx]
                line['end'] = len(sol_set) if line['end'] == -1 else line['end']
                for ind in range(line['start'], line['end'], line['skip']+1):
                    sol = sol_set[ind]
                    sol.prepare(problem_data, mesh_size=self.mesh_size, overwrite=False)
                    # sol.prepare(problem_data)
                    line['data'].append({'x_data': sol.evaluate(line['x']),
                                         'y_data': sol.evaluate(line['y'])})
            else:
                raise ValueError('Invalid plot type specified')
