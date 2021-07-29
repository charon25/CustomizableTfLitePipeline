# -*- coding: utf-8 -*-

import logging
import os
import platform
import shutil
import string
import time
import wave

# import matplotlib.pyplot as plt
import numpy as np
import tflite_runtime.interpreter as tflite

from processes import Process


logger = logging.getLogger(__name__)
logging.basicConfig(format="%(asctime)s\t%(levelname)s\t%(name)s  %(message)s")
logger.setLevel(logging.DEBUG)

EDGE_TPU_LIB = {
  'Linux': 'libedgetpu.so.1',
  'Darwin': 'libedgetpu.1.dylib',
  'Windows': 'edgetpu.dll'
}[platform.system()]
logger.debug("Platform : %s - Edge TPU lib : %s", platform.system(), EDGE_TPU_LIB)

VALID_FILENAME_CHARS = "-_.(),;!@=+{}{}".format(string.ascii_letters, string.digits)


class Processing:
    def __init__(self, config, client_id):
        try:
            self.delegate = tflite.load_delegate(EDGE_TPU_LIB)
        except:
            logger.warning('EdgeTPU not found')

        self.config = config
        self.client_id = client_id
        self.parse_processes()

    def parse_processes(self):
        self.input_process = None
        self.middle_processes = {}
        for process in self.config.get_processes():
            if process.position == 'input':
                if self.input_process is not None:
                    raise ValueError("Cannot create two input processes.")

                self.input_process = Process.create_process(process)
            else:
                self.middle_processes[process.name] = Process.create_process(process)

        if self.input_process is None:
            raise ValueError('No input process.')


    def _load_audio(self, filename):
        with wave.open(filename, 'rb') as wr:
            audio = wr.readframes(wr.getnframes())

        audio = np.frombuffer(audio, dtype=np.int16)
        if len(audio.shape) > 1:
            audio = np.mean(audio, axis=1)

        return audio.astype(np.float32) / 32768.0


    def get_actions(self, process, result):
        yield from process.get_on_result_actions(result)
        yield from process.get_on_not_result_actions(result)
        yield from process.get_always_actions()


    def get_next_process(self, action, data, result):
        process = self.middle_processes.get(action.target, False)
        if not process:
            raise ValueError("No process with name '{}' to continue pipe.".format(action.target))

        if action.input == 'same':
            data = np.copy(data)
        elif action.input == 'result':
            data = np.copy(result)
        else:
            raise ValueError("`input` field of the 'next' action should be 'same' or 'result'.")
        
        return (process, data)


    def _get_filename(self, process, action):
        filename = action.filename
        if filename == "default":
            filename = "%d-%n-%R.wav"

        filename = process.replace_string(str(filename), self.client_id)
        # Remove invalid characters from filename
        filename = ''.join([c if c in VALID_FILENAME_CHARS else '_' for c in filename])
        if not filename.endswith('.wav'):
            filename += '.wav'

        return filename
    
    def _get_directory(self, process, action):
        directory = action.directory
        if directory is None or directory == "default":
            directory = os.path.join(self.config.directories.save_dir, '%c')

        directory = process.replace_string(str(directory), self.client_id)

        if not os.path.isdir(directory):
            os.makedirs(directory)
        return directory

    def save_audio(self, process, action, source_filename):
        filename = self._get_filename(process, action)
        directory = self._get_directory(process, action)
        filepath = os.path.join(directory, filename)

        shutil.copy(source_filename, filepath)
        return filepath


    def log_results(self, process, line):
        if line == 'default':
            line = "Process '%n' -> Result : '%r'"

        logger.info(
            '%s',
            process.replace_string(str(line), self.client_id)
        )


    def process(self, filename):
        audio = self._load_audio(filename)
        data = audio.copy()
        process = self.input_process
        return_result = False
        returned_data = {}

        while True:
            results = process.process(np.copy(data))
            classes = results['classes']
            returned_data.update(results)

            if process.log:
                self.log_results(process, process.log)

            new_process = False
            return_result = False

            for action in self.get_actions(process, classes):
                if action.action is None:
                    pass
                elif action.action == 'next':
                    if new_process:
                        raise ValueError("Un process ne peut pas renvoyer dans deux process différents.")

                    new_process, data = self.get_next_process(action, data, classes)
                elif action.action == 'save':
                    filepath = self.save_audio(process, action, filename)
                    returned_data['filepath'] = filepath
                elif action.action == 'log':
                    self.log_results(process, action.line)
                elif action.action == 'output':
                    return_result = True
                else:
                    raise ValueError("Unknown action type '{}'.".format(action.action))


            if not new_process:
                break
            process = new_process

        if return_result:
            return returned_data

if __name__ == '__main__':
    from config import Config
    processing = Processing(Config('config-pc.yml'), 'client')
    # print(list(processing.input_process.get_on_result_actions(['false', 'false', 'false', 'bro', 'wes', 'wes'])))
    print(processing.process("others/3sec2.wav"))