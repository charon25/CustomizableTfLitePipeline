# -*- coding: utf-8 -*-

from collections import Counter
import re


class ActionTrigger:
    PERCENTAGE_REGEX = r'^([\w ,:!§\/.?-]+)([<>=]=?)([\d.]+)%$'
    ABSOLUTE_REGEX = r'^([\w ,:!§\/.?-]+)([<>=]=?)(\d+)$'

    def __init__(self, condition):
        if self._is_percentage(condition):
            self.keyword, self.operator, self.percentage_threshold = re.findall(ActionTrigger.PERCENTAGE_REGEX, condition)[0]
            self.percentage_threshold = float(self.percentage_threshold)
            self.is_valid = self._percentage_match

        elif self._is_absolute_number(condition):
            self.keyword, self.operator, self.count_threshold = re.findall(ActionTrigger.ABSOLUTE_REGEX, condition)[0]
            self.count_threshold = int(self.count_threshold)
            self.is_valid = self._absolute_match

        else:
            self.keyword = condition
            self.is_valid = self._exact_match

    def _is_percentage(self, condition):
        return re.match(ActionTrigger.PERCENTAGE_REGEX, condition)

    def _is_absolute_number(self, condition):
        return re.match(ActionTrigger.ABSOLUTE_REGEX, condition)


    def _exact_match(self, result):
        return ','.join(result) == self.keyword

    def _compare(self, number_1, number_2):
        if self.operator == '>':
            return number_1 > number_2
        elif self.operator == '>=':
            return number_1 >= number_2
        elif self.operator == '==':
            return number_1 == number_2
        elif self.operator == '<=':
            return number_1 <= number_2
        elif self.operator == '<':
            return number_1 < number_2

    def _percentage_match(self, result):
        counter = Counter(result)
        percentage = 100 * counter[self.keyword] / len(result)
        return self._compare(percentage, self.percentage_threshold)
    
    def _absolute_match(self, result):
        counter = Counter(result)
        count = counter[self.keyword]
        return self._compare(count, self.count_threshold)


class ActionTriggerCollection:
    def __init__(self, conditions):
        conditions = str(conditions).lower()

        conditions = conditions.split(';')
        self.triggers = [ActionTrigger(condition) for condition in conditions]
    
    def is_valid(self, result):
        return all(trigger.is_valid(result) for trigger in self.triggers)
