import yaml


class DotDict(dict):
    """
    Dictionary wrapper which allows to call keys with a dot (.).
    
    Exemple : 
    >>> d = {'key1': 1, 'key2': 2}
    >>> d = DotDict(d)
    >>> d.key1
        1
    """

    def __getattr__(*args):
        val = dict.get(*args)
        return DotDict(val) if type(val) is dict else val
    
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

class Config:
    def __init__(self, config_path):
        self._config = DotDict(yaml.safe_load(open(config_path, 'r', encoding='utf-8')))
        self._processes_by_name = {}
        for process in self.processes:
            self._processes_by_name[process['name']] = DotDict(process)

    def __getattr__(self, attr):
        return self._config.__getattr__(attr)
    
    def get_processes(self):
        """Return all the processes as DotDicts."""

        for process in self.processes:
            yield DotDict(process)

if __name__ == '__main__':
    config = Config('config.yml')
    print(config._config)