# -*- coding: utf-8 -*-

from collections import Counter
import enum
import operator
import os
import random
import re
import time
import wave

import numpy as np
import fake_librosa as librosa
import tflite_runtime.interpreter as tflite

from config import DotDict
from action_trigger import ActionTriggerCollection


class Preprocess:
    """
    Class which contains all the pre-processing algorithms.

    To add a new one, create a new function and add a new line in __init__.
    """

    def __init__(self, preprocess):
        if preprocess is None:
            self.process = self._none
        elif preprocess == 'mfcc':
            self.process = self._mfcc
        else:
            raise ValueError("Unknown preprocess : '{}'".format(preprocess))
    
    def _none(self, audio):
        return audio
    
    def _mfcc(self, audio):
        """Return MFCC transform of the sound."""

        data = np.transpose(librosa.feature.mfcc(y=audio.reshape((-1)), sr=16000, n_mfcc=32, hop_length=1001))
        data = np.expand_dims(data, axis=0)
        data = np.expand_dims(data, axis=-1)
        return data


class Process:
    """Class to manage processes of the pipe.
    To create a new one, make a new class inheriting this one and overload the `process` method.
    This method sould return `self.results` which is of the following form :

    {'classes': [list of returned names], 'values': [corresponding values], 'params': {any necessary params}}

    The `process` method should call `self._clear_results()` before doing anything to `self.results`
    then `self._normalize_results()` before returning.
    """

    def __init__(self, process):
        self.name = process.name
        self.model_outputs = []
        self.results = None
        self.shape = process.config.input_shape

        self.interpreter = tflite.Interpreter(model_path=process.model)
        self.input_layer = self.interpreter.get_input_details()[0]['index']
        self.output_layers = []
        for output_details in self.interpreter.get_output_details():
            self.output_layers.append(output_details['index'])
        print(self.name, self.output_layers)
        # self.output_layer = self.interpreter.get_output_details()[0]['index']
        self.interpreter.resize_tensor_input(self.input_layer, self.shape, strict=True)
        self.interpreter.allocate_tensors()

        self.preprocessing = Preprocess(process.config.preprocess)

        self.log = process.log

        self._create_on_result_actions(process)
        self._create_on_not_result_actions(process)
        self._create_always_actions(process)

    def _get_model_output(self, data, return_input_data=False):
        """Return output of the model, with or without the input data."""

        data = data.reshape(self.shape)
        data = self.preprocessing.process(data)

        self.interpreter.set_tensor(self.input_layer, data.astype('float32'))
        self.interpreter.invoke()

        self.model_outputs = {}
        for index in self.output_layers:
            self.model_outputs[index] = self.interpreter.get_tensor(index)

        if return_input_data:
            return (data, self.model_outputs[self.output_layers[0]])
        else:
            return self.model_outputs[self.output_layers[0]]

    def _create_on_result_actions(self, process):
        """Create all the "on_result" actions of the process as ActionTriggerCollections."""

        self.on_result_actions = list()
        
        if process.actions is None or process.actions.on_result is None:
            return
        
        for action_dict in process.actions.on_result:
            condition, action = list(action_dict.items())[0]
            action_triggers = ActionTriggerCollection(condition)
            self.on_result_actions.append((action_triggers, DotDict(action)))

    def _create_on_not_result_actions(self, process):
        """Create all the "on_not_result" actions of the process as ActionTriggerCollections."""

        self.on_not_result_actions = list()

        if process.actions is None or process.actions.on_not_result is None:
            return

        for action_dict in process.actions.on_not_result:
            condition, action = list(action_dict.items())[0]
            action_triggers = ActionTriggerCollection(condition)
            self.on_not_result_actions.append((action_triggers, DotDict(action)))
        
    def _create_always_actions(self, process):
        """Create all the "always" actions of the process."""

        self.on_always_actions = list()

        if process.actions is None or process.actions.always is None:
            return

        for action in process.actions.always:
            self.on_always_actions.append(DotDict(action))


    def get_on_result_actions(self, result):
        """Generator for all the "on_result" actions satisfying the given result."""

        for action_trigger, action in self.on_result_actions:
            if action_trigger.is_valid(result):
                yield action

    def get_on_not_result_actions(self, result):
        """Generator for all the "on_not_result" actions satisfying the given result."""

        for action_trigger, action in self.on_not_result_actions:
            if not action_trigger.is_valid(result):
                yield action
    
    def get_always_actions(self):
        """Yield all the always actions"""

        yield from self.on_always_actions
    
    
    def replace_string(self, string, client_id, shortened=False):
        """Replace the CustomString with all the necessary fields. Add more if needed."""

        string = string.replace('%n', self.name.lower())
        string = string.replace('%r', str(self.results['classes']).lower()[:50])
        string = string.replace('%R', str(self.results['classes']).lower())
        string = string.replace('%d', time.strftime('%Y_%m_%d-%H_%M_%S'))
        string = string.replace('%a', str(random.randint(1000, 9999)))
        string = string.replace('%c', client_id)
        return string

    def _clear_results(self):
        """Clear the `self.results` variable."""

        self.results = {
            'classes': [],
            'values': [],
            'params': {}
        }

    def _normalize_results(self):
        """Check that `self.results` is of the right form, and convert to string and uncapitalize every class."""

        if not isinstance(self.results, dict) or 'classes' not in self.results or 'values' not in self.results:
            raise ValueError("Incorrect `self.results` format : {}".format(self.results))

        self.results['classes'] = list(map(lambda res: str(res).lower(), self.results['classes']))

    def get_result_of_layer(self, index):
        print(self.name, index, self.output_layers)
        if index >= len(self.output_layers):
            raise IndexError('Model only has {} layers, and you tried to access index {}'.format(len(self.output_layers), index))

        layer_index = self.output_layers[index]

        if self.model_outputs is None:
            raise ValueError('Model outputs have not been computed yet.')
        if not layer_index in self.model_outputs:
            raise IndexError("Model has no layer of index {}".format(layer_index))
        
        return self.model_outputs[layer_index]


    @staticmethod
    def create_process(process):
        """Create the right Process class based on the DotDict."""

        if process.type == 'anomaly':
            return AnomalyProcess(process)
        elif process.type == 'classification':
            return ClassificationProcess(process)
        else:
            raise ValueError("Unknown process type : '{}'.".format(process.type))


class AnomalyProcess(Process):
    """
    Process that returns True or False, depending of if the sound contains anomalies.
    
    `self.results['class']` contains 'true' or 'false'.

    `self.results['values']` contains the difference between generated and real.

    `self.results['params']` contains the threshold used.
    """

    def __init__(self, process):
        super().__init__(process)
        self.threshold = process.config.threshold
    
    def process(self, data):
        data, results = self._get_model_output(data, return_input_data=True)

        self._clear_results()

        self.results['values'] = np.max(np.abs(data - results), axis=(1, 2))
        self.results['classes'] = self.results['values'] > self.threshold
        self.results['params']['threshold'] = self.threshold
        self._normalize_results()
        return self.results


class ClassificationProcess(Process):
    """
    Process that classify the audio in different classes.
    
    `self.results['class']` contains the classes name.

    `self.results['values']` contains the classes confidence.

    `self.results['params']` contains the count and minimum confidence.
    """

    def __init__(self, process):
        super().__init__(process)
        self.load_labels(process.config.labels)
        self.minimum_confidence = process.config.minimum_confidence or 0.0
        self.count = process.config.count or len(self.labels)
        if self.count <= 0:
            self.count = len(self.labels)


    def load_labels(self, labels):
        """Read the labels from the file. The file should have one label per line, in the form '<index>,<label>'."""

        if not os.path.isfile(labels):
            raise FileNotFoundError("Labels file '{}' not found.".format(labels))
        
        self.labels = {}
        with open(labels, 'r', encoding='utf-8') as fi:
            for line in fi.read().splitlines():
                if line == '':
                    continue
                index, names = line.split(',')
                self.labels[int(index)] = names.lower()

    def process(self, data):
        raw_results = self._get_model_output(data, return_input_data=False)

        sorted_indexes = raw_results.argsort(1)[:, -self.count:]
        sorted_results  = np.sort(raw_results, 1)[:, -self.count:]

        self._clear_results()

        for y, row in enumerate(sorted_indexes):
            for x, ind in reversed(list(enumerate(row))):
                confidence = sorted_results[y, x]
                if confidence >= self.minimum_confidence and ind in self.labels:
                    self.results['classes'].append(self.labels[ind])
                    self.results['values'].append(confidence)
                else:
                    self.results['classes'].append('N/A')
                    self.results['values'].append(0.0)

        self.results['params']['count'] = self.count
        self.results['params']['min_confidence'] = self.minimum_confidence
        self._normalize_results()
        return self.results
