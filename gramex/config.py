'Manages YAML config files as layered configurations with imports.'

import yaml
import logging
from pathlib import Path
from copy import deepcopy
from orderedattrdict import AttrDict
from orderedattrdict.yamlutils import AttrDictYAMLLoader


def walk(node):
    'Bottom-up recursive walk through nodes yielding key/index, value, node'
    if hasattr(node, 'items'):
        for key, value in node.items():
            for item in walk(value):
                yield item
            yield key, value, node
    elif isinstance(node, list):
        for index, value in enumerate(node):
            for item in walk(value):
                yield item
            yield index, value, node


def merge(old, new, overwrite=False):
    '''
    Update old dict with items in new. If old[key] is a dict, update old[key]
    with new[key] to preserve existing keys in old[key].

        >>> merge({'a': {'x': 1}}, {'a': {'y': 2}})
        {'a': {'x': 1, 'y': 2}}

    If ``overwrite=True``, the old dict is overwritten. By default, a new
    deepcopy is created.
    '''
    result = old if overwrite else deepcopy(old)
    for key in new:
        if key in result and hasattr(result[key], 'items'):
            merge(result[key], new[key], overwrite=True)
        else:
            result[key] = new[key]
    return result


class ChainConfig(AttrDict):
    '''
    An AttrDict that manages multiple configurations as layers.

        >>> config = ChainConfig([
        ...     ('base', PathConfig('gramex.yaml')),
        ...     ('app1', PathConfig('app.yaml')),
        ...     ('app2', AttrDict())
        ... ])

    Any dict-compatible values are allowed. ``+config`` returns the merged values.
    '''

    def __pos__(self):
        '+config returns layers merged in order, removing null keys'
        conf = AttrDict()
        for name, config in self.items():
            if hasattr(config, '__pos__'):
                config.__pos__()
            conf = merge(conf, config)

        # Remove keys where the value is None
        for key, value, node in walk(conf):
            if value is None:
                del node[key]

        return conf


def _open(path, default=AttrDict()):
    'Load a YAML path.Path as an ordered AttrDict'
    path = path.absolute()
    if not path.exists():
        logging.warn('Missing config: %s', path)
        return default
    logging.debug('Loading config: %s', path)
    with path.open() as handle:
        result = yaml.load(handle, Loader=AttrDictYAMLLoader)
    if result is None:
        logging.warn('Empty config: %s', path)
        return default
    return result


def _pathstat(path):
    'Freeze path along current status, returning an AttrDict'
    # If path doesn't exist, create a dummy stat structure with
    # safe defaults (old mtime, 0 filesize, etc)
    stat = path.stat() if path.exists() else AttrDict(st_mtime=0, st_size=0)
    return AttrDict(path=path, stat=stat)


# TODO: Generalise load-processing
def _imports(node, source):
    '''
    Parse import: in the node relative to the source path.
    Return imported pathtime in the order they were imported.
    '''
    imported_paths = [_pathstat(source)]
    root = source.absolute().parent
    for key, value, node in walk(node):
        if key == 'import':
            for name, pattern in value.items():
                paths = root.glob(pattern) if '*' in pattern else [Path(pattern)]
                for path in paths:
                    new_conf = _open(path)
                    imported_paths += [_pathstat(path)] + _imports(new_conf, source=path)
                    merge(node, new_conf)
            # Delete the import key
            del node[key]
    return imported_paths


class PathConfig(AttrDict):
    '''
    An ``AttrDict`` that is loaded from a path as a YAML file. For e.g.,
    ``conf = PathConfig(path)`` loads the YAML file at ``path`` as an AttrDict.
    ``+conf`` reloads the path if required.

    Like http://configure.readthedocs.org/ but supports imports not inheritance.
    This lets us import YAML files in the middle of a YAML structure::

        key:
            import:
                conf1: file1.yaml       # Import file1.yaml here
                conf2: file2.yaml       # Import file2.yaml here

    Each ``PathConfig`` object has an ``__info__`` attribute with the following
    keys:

    __info__.path
        The path that this instance syncs with, stored as a ``pathlib.Path``
    __info__.imports
        A list of imported files, stored as an ``AttrDict`` with 2 attributes:

        path
            The path that was imported, stored as a ``pathlib.Path``
        stat
            The ``os.stat()`` information about this file (or ``None`` if the
            file is missing.)
    '''
    def __init__(self, path):
        super(PathConfig, self).__init__()
        self.__info__ = AttrDict(path=Path(path), imports=[])
        self.__pos__()

    def __pos__(self):
        '+config reloads a layer named name (if it has a path)'
        path = self.__info__.path

        # We must reload the layer if nothing has been imported...
        reload = not self.__info__.imports
        # ... or if an imported file is deleted / updated
        for imp in self.__info__.imports:
            exists = imp.path.exists()
            if not exists and imp.stat is not None:
                reload = True
                logging.info('Deleted config: %s', imp.path)
                break
            if exists and (imp.path.stat().st_mtime > imp.stat.st_mtime or
                           imp.path.stat().st_size != imp.stat.st_size):
                reload = True
                logging.info('Updated config: %s', imp.path)
                break
        if reload:
            self.clear()
            self.update(_open(path))
            self.__info__.imports = _imports(self, path)
        return self
