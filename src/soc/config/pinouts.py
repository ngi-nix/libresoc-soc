import os
import sys
import json
from pprint import pprint
from collections import OrderedDict


def _byteify(data, ignore_dicts = False):
    # if this is a unicode string, return its string representation
    try:
        if isinstance(data, unicode):
            return data.encode('utf-8')
    except NameError:
        return data
    # if this is a list of values, return list of byteified values
    if isinstance(data, list):
        return [ _byteify(item, ignore_dicts=True) for item in data ]
    # if this is a dictionary, return dictionary of byteified keys and values
    # but only if we haven't already byteified it
    if isinstance(data, dict) and not ignore_dicts:
        return OrderedDict((_byteify(key, ignore_dicts=True),
                    _byteify(value, ignore_dicts=True))
                        for key, value in data.iteritems())
    # if it's anything else, return it in its original form
    return data


def get_pinspecs(chipname=None, subset=None):
    chip = load_pinouts(chipname)
    pinmap = chip['pins.map']
    specs = OrderedDict() # preserve order
    for k, bus in chip['pins.specs'].items():
        k, num = k.lower().split(":")
        name = '%s%s' % (k, num)
        if subset is None or name in subset:
            pins = []
            for pin in bus:
                pin = pin.lower()
                pname = '%s_%s' % (name, pin[:-1])
                if pname in pinmap:
                    newpin = pinmap[pname][2:]
                    newpin = '_'.join(newpin.split("_")[1:])
                    pin = newpin + pin[-1]
                pins.append(pin)
            specs['%s%s' % (k, num)] = pins
    return specs


def load_pinouts(chipname=None):
    """load_pinouts - loads the JSON-formatted dictionary of a chip spec

    note: this works only when pinmux is a correctly-initialised git submodule
    and when the spec has been actually generated.  see Makefile "make mkpinmux"
    """

    # default pinouts for now: ls180
    if chipname is None:
        chipname = 'ls180'

    # load JSON-formatted pad info from pinmux
    pth = os.path.abspath(__file__)
    pth = os.path.split(pth)[0]

    # path is relative to this filename, in the pinmux submodule
    pinmux = os.getenv("PINMUX", "%s/../../../pinmux" % pth)
    fname = "%s/%s/litex_pinpads.json" % (pinmux, chipname)
    with open(fname) as f:
        txt = f.read()

    # decode the json, strip unicode formatting (has to be recursive)
    chip = json.loads(txt, object_hook=_byteify)
    chip = _byteify(chip, ignore_dicts=True)

    return chip

if __name__ == '__main__':
    if sys.argv == 2:
        chipname = sys.argv[1]
    else:
        chipname = None
    chip = load_pinouts(chipname)
    for k, v in chip.items():
        print ("\n****", k, "****")
        pprint(v)
