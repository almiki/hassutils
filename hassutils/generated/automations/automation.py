

class Automation(object):
    def __init__(self, **kwargs):
        self._alias = kwargs.get('alias')
        self._triggers = kwargs.get('triggers') or [kwargs['trigger']]
        self._conditions = kwargs.get('conditions') or [c for c in [kwargs.get('condition')] if c]
        self._actions = kwargs.get('actions') or [kwargs['action']]

    def output(self, automation_id):
        lines = []

        lines.append("- id: '{}'".format(automation_id))

        indent = '  '
        indent_dash = '- '

        if self._alias:
            lines.append(indent + "alias: {}".format(self._alias))

        lines.append(indent + "trigger:")
        for trigger in self._triggers:
            lines.extend(indent + (indent if i > 0 else indent_dash) + l for i, l in enumerate(trigger.output()))

        if self._conditions:
            lines.append(indent + "condition:")
            for condition in self._conditions:
                lines.extend(indent + (indent if i > 0 else indent_dash) + l for i, l in enumerate(condition.output()))

        lines.append(indent + "action:")
        for action in self._actions:
            lines.extend(indent + (indent if i > 0 else indent_dash) + l for i, l in enumerate(action.output()))

        return lines

    @staticmethod
    def dump_automations(automations, id_prefix=''):
        lines = []

        for i, a in enumerate(automations):
            lines.extend(a.output(id_prefix + str(i + 1)))
            lines.append('')

        return '\n'.join(lines)


class BasicThing(object):
    def __init__(self, *args):
        self._args = list(args)

    def output(self):
        return self._args
