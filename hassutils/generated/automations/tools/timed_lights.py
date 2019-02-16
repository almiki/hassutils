import re
from hassutils.generated.automations.automation import Automation
from hassutils.generated.automations.trigger import Trigger
from hassutils.generated.automations.action import Action
from hassutils.generated.automations.condition import Condition


_time_re = re.compile(r"(\d\d)(?::(\d\d)(?::(\d\d))?)?")
_sun_re = re.compile(r"sun(set|rise)((-|\+)(?:(?:(\d\d):)?(\d\d):)?(\d\d))?")


def _calc_time(text):
    m = _time_re.match(text)
    if m is not None:
        hours = int(m.group(1))
        minutes = int(m.group(2) or 0)
        seconds = int(m.group(3) or 0)

        if 0 <= hours <= 23 and 0 <= minutes <= 59 and 0 <= seconds <= 60:
            return hours, minutes, seconds


def _calc_sun_time(text):
    m = _sun_re.match(text)
    if m is not None:
        kind = m.group(1)
        # offset = m.group(2)
        sign = m.group(3)
        hours = int(m.group(4) or 0)
        minutes = int(m.group(5) or 0)
        seconds = int(m.group(6) or 0)

        if not sign:
            return (kind, "00:00:00", (0, 0, 0))

        if 0 <= hours <= 23 and 0 <= minutes <= 59 and 0 <= seconds <= 60:
            mult = 1 if sign == '+' else -1
            return (kind, "{}{:02d}:{:02d}:{:02d}".format(sign, hours, minutes, seconds), tuple(mult * p for p in (hours, minutes, seconds)))


def _calc_seconds(time_tuple):
    assert len(time_tuple) == 3

    h, m, s = time_tuple
    return s + m * 60 + h * 60 * 60


def _format_template_time(h, m, s):
    return "strptime('{:02d}:{:02d}:{:02d}', '%H:%M:%S').time()".format(h, m, s)


class TimedLightAutomationMaker(object):
    """
    Creates automations that do the following:
    
    - Turn lights on/off at given times or sunset/sunrise + offset
    - Turn lights on/off at startup and optionally other events, based on whether the time is between the specified on and off times.
      Note: the event-driven trigger doesn't take into account sunrise/sunset offsets.

    """

    @staticmethod
    def get_automations(**kwargs):
        alias = kwargs.get('alias')

        on = kwargs['on']
        off = kwargs['off']
        entities = kwargs.get('entities') or [kwargs['entity']]
        restrict_entity = kwargs.get('restrict')
        events = kwargs.get('events', ())

        # min_on_duration = kwargs.get('min_on_duration')
        # random_delay = kwargs.get('random_delay')  # Delays the
        # random_shift = kwargs.get('random_shift')

        on_action, off_action = [
            Action("service: light.{}".format(oo),
                   "data:",
                   "  entity_id:",
                   *["  - {}".format(e) for e in entities]) for oo in ("turn_on", "turn_off")
        ]

        automations = []

        def add_automation(**kwargs):
            automations.append(Automation(**kwargs))

        on_time = _calc_time(on)
        off_time = _calc_time(off)

        on_sun = _calc_sun_time(on)
        off_sun = _calc_sun_time(off)

        conditions = []

        if restrict_entity:
            conditions.append(Condition("condition: state",
                                        "entity_id: {}".format(restrict_entity),
                                        "state: 'on'"))

        if on_time:
            add_automation(alias="{} (on)".format(alias) if alias else None,
                           trigger=Trigger("platform: time",
                                           "at: '{}'".format(on)),
                           conditions=conditions,
                           action=on_action)
        elif on_sun:
            add_automation(alias="{} (on)".format(alias) if alias else None,
                           trigger=Trigger("platform: sun",
                                           "event: sun{}".format(on_sun[0]),
                                           "offset: '{}'".format(on_sun[1])),
                           conditions=conditions,
                           action=on_action)
        else:
            assert False

        if off_time:
            add_automation(alias="{} (off)".format(alias) if alias else None,
                           trigger=Trigger("platform: time",
                                           "at: '{}'".format(off)),
                           conditions=conditions,
                           action=off_action)
        elif off_sun:
            add_automation(alias="{} (off)".format(alias) if alias else None,
                           trigger=Trigger("platform: sun",
                                           "event: sun{}".format(off_sun[0]),
                                           "offset: '{}'".format(off_sun[1])),
                           conditions=conditions,
                           action=off_action)
        else:
            assert False

        defs = [
            "{% set sunset = as_timestamp(state_attr('sun.sun', 'next_setting')) %}",
            "{% set sunrise = as_timestamp(state_attr('sun.sun', 'next_rising')) %}",
            "{% set now = now() %}",
            "{% set today = now.date() %}",
            "{% set twenty_hours = now.replace(hour=21) - now.replace(hour=1) %}",
            "{% set twenty_hours_from_now = now + twenty_hours %}",
            "{% set tomorrow = twenty_hours_from_now.date() if today.day != twenty_hours_from_now.day else (twenty_hours_from_now + twenty_hours).date() %}"
        ]

        if on_sun:
            defs.append("{{% set next_on_time = ({} + {}) %}}".format('sunset' if on_sun[0] == 'set' else 'sunrise', _calc_seconds(on_sun[2])))
        else:
            defs.append("{{% set t = strptime('{:02d}:{:02d}:{:02d}', '%H:%M:%S').replace(year=today.year, month=today.month, day=today.day) %}}".format(*on_time))
            defs.append("{% set next_on_time = as_timestamp(t if t.time() > now.time() else t.replace(year=tomorrow.year, month=tomorrow.month, day=tomorrow.day)) %}")

        if off_sun:
            defs.append("{{% set next_off_time = ({} + {}) %}}".format('sunset' if off_sun[0] == 'set' else 'sunrise', _calc_seconds(off_sun[2])))
        else:
            defs.append("{{% set t = strptime('{:02d}:{:02d}:{:02d}', '%H:%M:%S').replace(year=today.year, month=today.month, day=today.day) %}}".format(*off_time))
            defs.append("{% set next_off_time = as_timestamp(t if t.time() > now.time() else t.replace(year=tomorrow.year, month=tomorrow.month, day=tomorrow.day)) %}")

        defs.append("{% set on_off = 'on' if next_off_time < next_on_time and as_timestamp(now) < next_off_time - 30 else 'off' %}")

        auto_triggers = [
            ("recover", Trigger("platform: homeassistant",
                                "event: start"))
        ]

        for event in events:
            auto_triggers.append((event, Trigger("platform: event",
                                                 "event_type: {}".format(event))))

        if restrict_entity:
            auto_triggers.append(("restrict_enabled", Trigger("platform: state",
                                                              "entity_id: {}".format(restrict_entity),
                                                              "to: 'on'")))

        for trigger_reason, trigger in auto_triggers:
            action_lines = [ "service_template: >" ]
            action_lines.extend('  ' + d for d in defs)
            action_lines.extend(["  light.turn_{{ on_off }}",
                                 "data:",
                                 "  entity_id:", ] +
                                ["  - {}".format(e) for e in entities])

            add_automation(alias="{} ({})".format(alias, trigger_reason) if alias else None,
                           trigger=trigger,
                           conditions=conditions,
                           actions=[Action(*action_lines),
                                    ])
        return automations

    @staticmethod
    def parse(configs_text):
        """
        Format for text file:
        
            events=event1,event2,event_etc     # Events that will trigger light on/off to re-evaluate, optional
            
            <Pretty Light Name>, <on_time>, <off_time>, <light.light_id1>|<light.light_id2>|<...>, <input_boolean.enabler_id>    # Enabler is an input_boolean which controls whether the automation is enabled, optional
            Kitchen Lights, sunset+10:00, 23:30, light.kitchen_light|light.kitchen_light2   # 2 lights, on at 10 minutes after sunset, off at 11:30 PM
            Bedroom Light, 20:00, 02:00, light.bedroom_light, input_boolean.on_vacation     # On at 8 PM, off at 2 AM. Only active while on vacation.
            Outside Light, sunset-30:00, sunrise+30:00, light.outside_light                 # On 30 minutes before sunset, off 30 minutes after sunrise
        """

        events_re = re.compile("^events=(.*)$")

        tls = []
        events = []
        for line in configs_text.split('\n'):
            line = line.split('#', 1)[0].strip()
            if not line:
                continue

            events_match = events_re.match(line)
            if events_match is not None:
                events = [e.strip() for e in events_match.group(1).split(',')]
                continue

            parts = [p.strip() for p in line.split(',')]
            if len(parts) < 4:
                continue

            tls.extend(TimedLightAutomationMaker.get_automations(alias=parts[0],
                                                                 on=parts[1],
                                                                 off=parts[2],
                                                                 entities=parts[3].split("|"),
                                                                 restrict=parts[4] if len(parts) >= 5 else None,
                                                                 events=events))

        return tls


if __name__ == "__main__":
    tls = TimedLightAutomationMaker.parse("""
            events=event1,event2,event_etc     # Events that will trigger light on/off to re-evaluate, optional
            
            #<Pretty Light Name>, <on_time>, <off_time>, <light.light_id>, <input_boolean.enabler_id>    # Enabler is an input_boolean which controls whether the automation is enabled, optional
            Kitchen Light, sunset+10:00, 23:30, light.kitchen_light|light.kitchen_light2                         # On at 10 minutes after sunset, off at 11:30 PM
            Bedroom Light, 20:00, 02:00, light.bedroom_light, input_boolean.on_vacation     # On at 8 PM, off at 2 AM. Only active while on vacation.
            Outside Light, sunset-30:00, sunrise+30:00, light.outside_light                 # On 30 minutes before sunset, off 30 minutes after sunrise
    """)

    print(Automation.dump_automations(tls, "gen"))
