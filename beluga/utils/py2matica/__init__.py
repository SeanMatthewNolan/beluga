from .py2matica import mathematica_run
from .py2matica import mathematica_solve
__all__ = []
import os
import glob
modules = glob.glob(os.path.dirname(__file__)+"/*.py")
__all__ += ([ os.path.basename(f)[:-3] for f in modules])
