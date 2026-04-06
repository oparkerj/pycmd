from . import log
from . import meta
from . import module
from . import proc
from . import run
from . import settings

get_logger = log.get_logger
exec = meta.exec
main = meta.main
use_settings = meta.use_settings
path = module.get_path()
info = run.MainModuleInfo()
