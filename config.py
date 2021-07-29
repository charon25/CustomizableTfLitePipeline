import yaml


class DotDict(dict):
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
        for process in self.processes:
            yield DotDict(process)

if __name__ == '__main__':
    config = Config('config.yml')
    print(config._config)
    # proc = next(config.get_processes())
    # print(proc.actions.on_result)
    # proc = next(config.get_processes())
    # print(proc.actions.always)
    # print(type(proc.actions))
    # proc.actions.on_result.items()
    # for k, v in proc.actions.list_dicts():
    #     # k, v = list(actions.items())[0]
    #     # k, v = k
    #     print(k, v)
    # on_result = next(config.get_processes()).actions.on_result
    # for result, action in config.get_on_not_result_actions("anomalies"):
    #     print(type(action))
    # processes = {
    #     'input': None,
    #     'middle': [],
    #     'output': None
    # }
    # for process in config.get_processes():
    #     if process.position in processes:
    #         if type(processes[process.position]) == list:
    #             processes[process.position].append(process)
    #         else:
    #             processes[process.position] = process
    # print(processes)