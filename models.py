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
    """Class managing a full pipe of processes."""

    def __init__(self, config, client_id):
        try:
            self.delegate = tflite.load_delegate(EDGE_TPU_LIB)
        except:
            logger.warning('EdgeTPU not found')

        self.config = config
        self.client_id = client_id
        self.parse_processes()

    def parse_processes(self):
        """Analyse all the DotDict containing processes and get them as Process class."""

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
        """Read audio wave file and return it as a np float32 array between 0 and 1."""

        with wave.open(filename, 'rb') as wr:
            audio = wr.readframes(wr.getnframes())

        audio = np.frombuffer(audio, dtype=np.int16)
        if len(audio.shape) > 1:
            audio = np.mean(audio, axis=1)

        return audio.astype(np.float32) / (2**(8 * self.config.audio.sample_width - 1))


    def get_actions(self, process, result):
        """Generator of all the actions needed to be taken according to the result."""

        yield from process.get_on_result_actions(result)
        yield from process.get_on_not_result_actions(result)
        yield from process.get_always_actions()


    def get_next_process(self, action, data, result):
        """Return the next process in the pipeline and its input data."""

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
        """Get the filename for the 'save' action."""

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
        """Get the directory for the 'save' action."""

        directory = action.directory
        if directory is None or directory == "default":
            directory = os.path.join(self.config.directories.save_dir, '%c')

        directory = process.replace_string(str(directory), self.client_id)

        if not os.path.isdir(directory):
            os.makedirs(directory)
        return directory

    def save_audio(self, process, action, source_filename):
        """Save the audio in the right path."""

        filename = self._get_filename(process, action)
        directory = self._get_directory(process, action)
        filepath = os.path.join(directory, filename)

        shutil.copy(source_filename, filepath)
        return filepath


    def log_results(self, process, line):
        """Log results according to the 'line'."""

        if line == 'default':
            line = "Process '%n' -> Result : '%r'"

        logger.info(
            '%s',
            process.replace_string(str(line), self.client_id)
        )


    def process(self, filename):
        """Process the filename in the pipeline."""

        audio = self._load_audio(filename)
        data = audio.copy()
        process = self.input_process
        returned_data = {}

        while True:
            results = process.process(np.copy(data))
            classes = results['classes']

            if process.log:
                self.log_results(process, process.log)

            new_process = False

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
                    returned_data[process.name] = results.copy()
                else:
                    raise ValueError("Unknown action type '{}'.".format(action.action))


            if not new_process:
                break
            process = new_process

        return returned_data

if __name__ == '__main__':
    from config import Config
    processing = Processing(Config('config-pc.yml'), 'client')
    print(processing.process("others/3sec2.wav"))