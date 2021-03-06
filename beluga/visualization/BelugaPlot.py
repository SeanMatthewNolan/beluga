from . import renderers
from .elements import PlotList,Plot
from .renderers import BaseRenderer
import dill, inspect, logging

class BelugaPlot:
    """
    Manages the plotting framework
    """
    def __init__(self, filename='data.dill', renderer = 'matplotlib', default_step = -1, default_sol = -1, mesh_size=None):
        """
        Initializes plotting framework with given data file
        """
        self._plots = []
        self._figures = []
        self._plotconfig = {}
        self.global_settings = {}
        self.filename = filename
        self.default_step_idx = default_step
        self.default_sol_idx = default_sol
        self.mesh_size = mesh_size

        # TODO: Get default renderer information from global configuration
        if isinstance(renderer, BaseRenderer):
            # Use custom renderer object
            self.renderer = renderer
        else:
            # Load renderer from the list of existing classes
            self.renderer = None
            for name, obj in inspect.getmembers(renderers):
                if inspect.isclass(obj) and issubclass(obj, BaseRenderer):
                    if name.lower() == renderer.lower():
                        # Renderer initialized with its default settings
                        self.renderer = obj()
            if self.renderer is None:
                raise ValueError('Renderer '+renderer+' not found')

    def add_plot(self, step = None, sol = None):
        """
        Adds a new plot
            (alias for add_plot() in PlotList)
        """
        if step is None:
            step = self.default_step_idx
        if sol is None:
            sol = self.default_sol_idx
        plot = Plot(step, sol, self.mesh_size)
        self._plots.append(plot)
        return plot

    def render(self,show=True):
        with open(self.filename,'rb') as f:
            logging.info("Loading datafile ...")
            out = dill.load(f)
            logging.info("Loaded "+str(len(out['solution']))+" solution sets from "+self.filename)

        for plot in self._plots:
            plot.preprocess(out['solution'],out['problem_data'])
            fig = self.renderer.create_figure()
            self.renderer.render_plot(fig,plot)
            self._figures.append(fig)
        if show:
            self.show()

    def show(self):
        self.renderer.show_all()

    def plotconfig(varname,value=None):
        """
        Adds/updates settings affecting all plots
        """
        if isinstance(varname, dict):
            self._plotconfig.update(varname)
        else:
            self._plotconfig[varname] = value
        return self
