from .automation import BasicThing


class Condition(BasicThing):
    pass


class CompositeCondition(object):
    def __init__(self, kind, conditions):
        assert kind in ("and", "or"), kind

        self._kind = kind
        self._conditions = conditions

    def output(self):
        lines = [
            "condition: {}".format(self._kind),
            "conditions:",
        ]

        for condition in self._conditions:
            lines.extend(('    ' if i > 0 else '  - ') + l for i, l in enumerate(condition.output()))

        return lines
