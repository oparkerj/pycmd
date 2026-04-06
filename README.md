This is a lightweight command wrapper I wrote for personal use.
The goal was to make it easy to write and compose command-line scripts in Python.

## Setup
Add the `bin` directory to the `PATH` variable, and use a shebang such as
`#!/usr/bin/env pycmd` to run a script via pycmd.

Pycmd may also be run directly as a python module.

## Usage
The simplest way to start is to have an executable file run via pycmd and define
an entry point.
```python
#!/usr/bin/env pycmd
import pycmd

@pycmd.main
def main():
    print("Example script")
```
This will run the main function using the [default pycmd setup](#default-pycmd-setup).

## Settings
The following settings control the execution of pycmd.

### Environment Variables
#### PYCMD_PATH
This variable is similar to `PYTHONPATH`, but is used to
control where pycmd looks when importing submodules from `pycmd.module`. This value
can be modified at runtime via `pycmd.path`, similar to `sys.path`.

#### PYCMD_LOGS
This specifies the directory where pycmd logs are generated. Logs are also pruned
from this directory. (default: `~/.pycmd`)

#### PYCMD_PRUNE
When using the default pycmd setup, this specifies the number of logs to retain
when pruning old logs. Set to a negative value to disable pruning. (default: 10)

### Configuration Options
Pycmd settings provide a way to share options between pycmd modules However, most
control over the behavior of a script will typically happen via standard CLI
arguments.
#### log
This option controls whether a log file is generated (default: true).

#### log_level
Controls the log level of the pycmd log file. (default: `logging.NOTSET`)

#### log_dir
Same as the environment variable `PYCMD_LOGS`. This option takes precedence over the
environment variable.

### Applying Options
#### On the main function
When using the default pycmd setup, settings are applied by reading the settings
metadata from the main function. This metadata can be set with the `use_settings`
decorator.
```python
@pycmd.main
@pycmd.use_settings(log=False)
def main():
    print("Script without log")
```

#### In CLI Arguments
When executing any pycmd script, the `--pycmd` argument can be given to define
*user settings*.
Simply giving an option name will give the option a value of `True`.
Prefixing the option with `~` will give it a value of `False`.
Using the form `name=value` will coerce the value to a Python type depending on
the content.
* "true" or "false" will be converted to `bool`
* "f" suffix will be converted to `float`.
* "hz" suffix will be converted to `float` representing delta time in seconds.
* "0x" prefix will convert a hexadecimal value to `int`.
* If the value is single (`'`) or double (`"`) quoted, the value will be an unquoted
`str`.
* If none of the above rules match, will attempt to convert the value to `int`, and
if that fails, the value is the verbatim string.

## Execution
Command format: `pycmd <SCRIPT> [ARGS...]`  
Executing pycmd does the following:
### Load the Main Module
pycmd loads the main module, which is specified by the `SCRIPT` argument. This module
is accessible at runtime via `import pycmd.main` or via `pycmd.info.module` during
the exec phase.
### Exec
`pycmd.run.exec(module)` is executed on the main module. This searches for a function
with "exec" metadata, and calls it. If such a function doesn't exist,
`pycmd.run.main(module)` is called instead, which runs the default pycmd setup.
### Default pycmd setup
This is the default configuration that pycmd executes unless an "exec" function is
defined on the main module. The default setup performs the following actions:
* Clear settings any apply any "settings" metadata defined on the main function.
* Apply user settings.
* Initialize console logging. Console output is captured, line-buffered, and emitted
to the pycmd logger.
* Initialize the log file.
* Log statistics such as the script arguments and cwd.
* Execute the main function.
* Log the execution time of the main function.
* Prune log files.